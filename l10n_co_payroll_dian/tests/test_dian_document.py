import base64
from datetime import datetime, timedelta

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from odoo.tests.common import TransactionCase, tagged

from ..models.cune_calculator import calculate_cune
from ..models.dian_soap_client import DianSOAPClient, DianSoapClient
from ..models.xml_builder_nomina import build_nomina_xml


@tagged("post_install", "-at_install")
class TestCoPayrollDianDocument(TransactionCase):
    def test_generate_signs_and_validates_xsd(self):
        company = self.env.company
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Prueba DIAN")])
        certificate = x509.CertificateBuilder().subject_name(subject).issuer_name(issuer).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(datetime.utcnow() - timedelta(days=1)).not_valid_after(datetime.utcnow() + timedelta(days=30)).sign(key, hashes.SHA256())
        p12 = pkcs12.serialize_key_and_certificates(b"test", key, certificate, None, serialization.NoEncryption())
        company.write({"vat": "900123456", "co_dian_payroll_enabled": True, "co_dian_software_id": "software-test", "co_dian_software_pin": "pin-test", "co_dian_certificate": base64.b64encode(p12), "co_dian_certificate_password": ""})
        employee = self.env["hr.employee"].create({"name": "Empleado Firmado", "company_id": company.id, "identification_id": "123456789"})
        period = self.env["l10n.co.payroll.period"].create({"company_id": company.id, "date_from": "2026-05-01", "date_to": "2026-05-15", "payment_date": "2026-05-15", "state": "ready"})
        line = self.env["l10n.co.payroll.period.line"].create({"period_id": period.id, "employee_id": employee.id, "basic_wage": 2500000, "gross_wage": 2500000, "deduction_total": 0, "worked_days": 15})
        document = self.env["l10n.co.payroll.dian.document"].create({"company_id": company.id, "period_id": period.id, "period_line_id": line.id})
        document.action_generate()
        self.assertEqual(document.state, "validated")
        self.assertTrue(document.xml_file)
        self.assertTrue(document.zip_file)
        self.assertFalse(document.xml_validation_errors)

    def test_soap_exposes_individual_cune_status_operation(self):
        self.assertIn("GetStatus", DianSoapClient.ACTIONS)
        self.assertIn("GetStatusZip", DianSoapClient.ACTIONS)
        self.assertNotEqual(DianSoapClient.ACTIONS["GetStatus"], DianSoapClient.ACTIONS["GetStatusZip"])

    def test_send_nomina_sync_uses_only_content_file(self):
        client = object.__new__(DianSOAPClient)
        client.build_envelope = lambda operation, body: body
        client.send = lambda operation, body: body
        body = client.send_nomina_sync("BASE64_ZIP")
        self.assertEqual(body.tag, "{%s}SendNominaSync" % client.DIAN_NS)
        self.assertIsNotNone(body.find("{%s}contentFile" % client.DIAN_NS))
        self.assertIsNone(body.find("{%s}fileName" % client.DIAN_NS))

    def test_get_status_uses_cune_as_track_id(self):
        client = object.__new__(DianSOAPClient)
        client.build_envelope = lambda operation, body: body
        client.send = lambda operation, body: body
        body = client.get_status("cune-96")
        self.assertEqual(body.tag, "{%s}GetStatus" % client.DIAN_NS)
        self.assertEqual(body.find("{%s}trackId" % client.DIAN_NS).text, "cune-96")

    def test_unmapped_earning_is_explicitly_sent_as_other_concept(self):
        company = self.env.company
        company.write({"vat": "900123456", "co_dian_payroll_enabled": True, "co_dian_software_id": "software-test", "co_dian_software_pin": "pin-test"})
        employee = self.env["hr.employee"].create({"name": "Empleado Concepto", "company_id": company.id, "identification_id": "123456789"})
        period = self.env["l10n.co.payroll.period"].create({"company_id": company.id, "date_from": "2026-05-01", "date_to": "2026-05-15", "payment_date": "2026-05-15", "state": "ready"})
        line = self.env["l10n.co.payroll.period.line"].create({"period_id": period.id, "employee_id": employee.id, "basic_wage": 2500000, "gross_wage": 2700000, "deduction_total": 0, "worked_days": 15})
        document = self.env["l10n.co.payroll.dian.document"].create({"company_id": company.id, "period_id": period.id, "period_line_id": line.id})
        context = document._build_context()
        self.assertEqual(context["xml_categories"]["devengados"]["otro_concepto_s"], 200000.0)
        self.assertIn(b"Otros conceptos de n\xc3\xb3mina", build_nomina_xml(context))

    def test_cune_is_sha384_and_document_context_is_complete(self):
        company = self.env.company
        company.write({"vat": "900123456", "co_dian_payroll_enabled": True, "co_dian_software_id": "software-test", "co_dian_software_pin": "pin-test"})
        employee = self.env["hr.employee"].create({
            "name": "Laura García López",
            "company_id": company.id,
            "identification_id": "123456789",
        })
        period = self.env["l10n.co.payroll.period"].create({
            "company_id": company.id,
            "date_from": "2026-05-01",
            "date_to": "2026-05-15",
            "payment_date": "2026-05-15",
            "state": "ready",
        })
        line = self.env["l10n.co.payroll.period.line"].create({
            "period_id": period.id,
            "employee_id": employee.id,
            "basic_wage": 2500000,
            "gross_wage": 2662000,
            "deduction_total": 0,
            "worked_days": 15,
        })
        document = self.env["l10n.co.payroll.dian.document"].create({
            "company_id": company.id,
            "period_id": period.id,
            "period_line_id": line.id,
        })
        context = document._build_context()
        self.assertEqual(document._validate_context(context), [])
        self.assertEqual(len(calculate_cune({"NumeroCompleto": "NOM00000001"})), 96)
        self.assertEqual(context["tipo_xml"], "102")
        self.assertEqual(context["totals"]["devengados_total"], 2662000.0)
        xml = build_nomina_xml(context)
        self.assertIn(b"NominaIndividual", xml)
        self.assertIn(context["cune"].encode(), xml)

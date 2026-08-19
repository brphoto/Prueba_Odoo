from odoo.tests.common import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestPortalSecurity(HttpCase):
    """Regresión de seguridad para el portal del empleado: cada ruta debe
    quedar acotada al empleado del usuario logueado (vía _get_employee),
    nunca a un id recibido por URL/query string. Cubre el patrón de
    aislamiento revisado manualmente en /loan/user y la descarga de
    adjuntos en /employee/documents/<id>."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        portal_group = cls.env.ref("base.group_portal")

        cls.employee_a = cls.env["hr.employee"].create({
            "name": "Portal Empleado A QA",
            "work_email": "qa.portal.a@example.invalid",
        })
        cls.employee_b = cls.env["hr.employee"].create({
            "name": "Portal Empleado B QA",
            "work_email": "qa.portal.b@example.invalid",
        })
        cls.user_a = cls.env["res.users"].create({
            "name": "Portal Empleado A QA",
            "login": "qa.portal.a@example.invalid",
            "email": "qa.portal.a@example.invalid",
            "password": "qa.portal.a@example.invalid",
            "group_ids": [(6, 0, [portal_group.id])],
        })
        cls.loan_a = cls.env["hr.payslip.loans"].create({
            "name": "Préstamo A QA",
            "number": "QA-A-001",
            "employee_id": cls.employee_a.id,
            "amount": 100.0,
            "dues": 1,
        })
        cls.loan_b = cls.env["hr.payslip.loans"].create({
            "name": "Préstamo B QA",
            "number": "QA-B-001",
            "employee_id": cls.employee_b.id,
            "amount": 200.0,
            "dues": 1,
        })
        cls.attachment_b = cls.env["ir.attachment"].create({
            "name": "documento_b.txt",
            "res_model": "hr.employee",
            "res_id": cls.employee_b.id,
            "datas": b"cQBh",  # base64 de contenido de prueba
        })

    def test_loan_user_list_only_shows_own_loans(self):
        self.authenticate("qa.portal.a@example.invalid", "qa.portal.a@example.invalid")
        response = self.url_open("/loan/user")
        self.assertEqual(response.status_code, 200)
        body = response.text
        # El template solo muestra loan.name (el "motivo"), no loan.number.
        self.assertIn("Préstamo A QA", body)
        self.assertNotIn("Préstamo B QA", body)

    def test_employee_document_download_blocks_other_employee_attachment(self):
        self.authenticate("qa.portal.a@example.invalid", "qa.portal.a@example.invalid")
        response = self.url_open("/employee/documents/%d" % self.attachment_b.id)
        self.assertEqual(response.status_code, 404)

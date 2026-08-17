import base64
import warnings

from datetime import timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization.pkcs12 import load_key_and_certificates

from odoo import _, fields, models
from odoo.exceptions import UserError


class CoPayrollDianCompany(models.Model):
    _inherit = "res.company"

    co_dian_payroll_enabled = fields.Boolean(
        string="Nómina electrónica DIAN",
        help="Activa la generación y transmisión de documentos soporte de nómina electrónica para esta compañía.",
    )
    co_dian_environment = fields.Selection(
        [("1", "Producción"), ("2", "Habilitación")],
        string="Ambiente DIAN",
        default="2",
        required=True,
    )
    co_dian_software_id = fields.Char(string="ID del software DIAN")
    co_dian_software_pin = fields.Char(string="PIN del software DIAN")
    co_dian_test_set_id = fields.Char(string="Test Set ID")
    co_dian_certificate = fields.Binary(string="Certificado digital PKCS#12")
    co_dian_certificate_filename = fields.Char(string="Nombre del certificado")
    co_dian_certificate_password = fields.Char(string="Contraseña del certificado")
    co_dian_certificate_id = fields.Many2one(
        "certificate.certificate",
        string="Certificado nativo Odoo",
        domain="[('company_id', '=', id)]",
    )
    co_dian_request_timeout = fields.Integer(string="Tiempo de espera DIAN (s)", default=90)
    co_dian_auto_check_pending = fields.Boolean(
        string="Consultar pendientes automáticamente",
        default=False,
        help="Permite que la tarea programada consulte estados pendientes sin intervención manual.",
    )
    co_dian_require_habilitation = fields.Boolean(
        string="Exigir habilitación antes de producción",
        default=False,
        help="Si está activo, bloquea envíos de producción hasta registrar 4 nóminas y 4 notas de ajuste aceptadas en habilitación.",
    )
    co_dian_certificate_subject = fields.Char(string="Titular del certificado", readonly=True, copy=False)
    co_dian_certificate_issuer = fields.Char(string="Emisor del certificado", readonly=True, copy=False)
    co_dian_certificate_serial = fields.Char(string="Serial del certificado", readonly=True, copy=False)
    co_dian_certificate_expiration = fields.Datetime(string="Vencimiento del certificado", readonly=True, copy=False)
    co_dian_certificate_fingerprint = fields.Char(string="Huella SHA-256", readonly=True, copy=False)
    co_dian_certificate_status = fields.Selection([
        ("valid", "Válido"), ("expired", "Vencido"), ("invalid", "Inválido"), ("missing", "Sin certificado"),
    ], string="Estado certificado", readonly=True, copy=False)
    co_dian_test_payroll_count = fields.Integer(string="Nóminas de habilitación aceptadas", compute="_compute_co_dian_habilitation")
    co_dian_test_adjustment_count = fields.Integer(string="Ajustes de habilitación aceptados", compute="_compute_co_dian_habilitation")
    co_dian_habilitation_ready = fields.Boolean(string="Habilitación mínima completada", compute="_compute_co_dian_habilitation")

    def _compute_co_dian_habilitation(self):
        document_model = self.env["l10n.co.payroll.dian.document"]
        for company in self:
            accepted = document_model.search([("company_id", "=", company.id), ("state", "=", "accepted"), ("submission_environment", "=", "2")])
            company.co_dian_test_payroll_count = len(accepted.filtered(lambda document: not document.is_adjustment))
            company.co_dian_test_adjustment_count = len(accepted.filtered("is_adjustment"))
            company.co_dian_habilitation_ready = company.co_dian_test_payroll_count >= 4 and company.co_dian_test_adjustment_count >= 4

    def _co_dian_signing_material(self):
        self.ensure_one()
        certificate = self.co_dian_certificate_id
        if certificate and certificate.pem_certificate and certificate.private_key_id and certificate.private_key_id.pem_key:
            return {
                "pem_certificate": certificate.pem_certificate,
                "pem_key": certificate.private_key_id.pem_key,
                "password": certificate.private_key_id.password or "",
            }
        if self.co_dian_certificate:
            return {
                "certificate_data": self.co_dian_certificate,
                "password": self.co_dian_certificate_password or "",
            }
        return {}

    def action_co_dian_validate_certificate(self):
        for company in self:
            material = company._co_dian_signing_material()
            if not material:
                raise UserError(_("Carga un certificado PKCS#12 o selecciona un certificado nativo de Odoo."))
            certificate = False
            if material.get("certificate_data"):
                try:
                    raw = base64.b64decode(material["certificate_data"])
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        private_key, certificate, _chain = load_key_and_certificates(
                            raw, (material.get("password") or "").encode("utf-8")
                        )
                    if not private_key or not certificate:
                        raise ValueError(_("el archivo no contiene llave privada y certificado"))
                except Exception as exc:
                    raise UserError(_("El certificado DIAN no se puede leer: %s") % exc) from exc
            elif material.get("pem_certificate"):
                try:
                    certificate = x509.load_pem_x509_certificate(base64.b64decode(material["pem_certificate"]))
                except Exception as exc:
                    raise UserError(_("El certificado nativo de Odoo no se puede leer: %s") % exc) from exc
            if not certificate:
                raise UserError(_("No se encontró un certificado utilizable."))
            expiration = getattr(certificate, "not_valid_after_utc", certificate.not_valid_after)
            if getattr(expiration, "tzinfo", None):
                expiration = expiration.astimezone(timezone.utc).replace(tzinfo=None)
            status = "valid" if expiration >= fields.Datetime.now() else "expired"
            company.write({
                "co_dian_certificate_subject": certificate.subject.rfc4514_string(),
                "co_dian_certificate_issuer": certificate.issuer.rfc4514_string(),
                "co_dian_certificate_serial": str(certificate.serial_number),
                "co_dian_certificate_expiration": fields.Datetime.to_string(expiration),
                "co_dian_certificate_fingerprint": certificate.fingerprint(hashes.SHA256()).hex(),
                "co_dian_certificate_status": status,
            })
        return {"type": "ir.actions.client", "tag": "display_notification", "params": {
            "title": _("Certificado válido"),
            "message": _("El material de firma se puede utilizar para firmar XML y autenticar SOAP."),
            "type": "success",
            "sticky": False,
        }}

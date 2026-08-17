import base64
import warnings

from datetime import timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization.pkcs12 import load_key_and_certificates

from odoo import _, api, fields, models
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
    co_dian_require_explicit_mapping = fields.Boolean(
        string="Exigir mapeo DIAN explícito",
        default=False,
        help="Bloquea la generación si una regla salarial no tiene un concepto DIAN configurado.",
    )
    co_dian_approval_mode = fields.Selection([
        ("none", "Sin aprobación de envío"),
        ("single", "Una aprobación"),
        ("double", "Doble aprobación"),
    ], string="Aprobación de envío DIAN", default="none", required=True,
        help="Controla si un usuario debe aprobar los documentos antes de transmitirlos.")
    co_dian_retry_enabled = fields.Boolean(
        string="Reintentos automáticos",
        default=True,
        help="Permite reintentar errores temporales de red o SOAP sin reenviar documentos ya identificados por DIAN.",
    )
    co_dian_max_retries = fields.Integer(string="Máximo de reintentos", default=3)
    co_dian_retry_delay_minutes = fields.Integer(string="Espera entre reintentos (minutos)", default=15)
    co_dian_certificate_alert_days = fields.Integer(string="Avisar certificado con días de anticipación", default=30)
    co_dian_notifications_enabled = fields.Boolean(
        string="Avisos operativos DIAN",
        default=True,
        help="Crea actividades internas cuando existan errores, pendientes antiguos o certificados próximos a vencer.",
    )
    co_dian_notify_errors = fields.Boolean(string="Avisar errores", default=True)
    co_dian_notify_pending = fields.Boolean(string="Avisar pendientes antiguos", default=True)
    co_dian_pending_alert_hours = fields.Integer(string="Horas para alertar un pendiente", default=4)
    co_dian_notify_certificate = fields.Boolean(string="Avisar certificado", default=True)
    co_dian_notify_user_ids = fields.Many2many(
        "res.users", "co_dian_notify_user_rel", "company_id", "user_id", string="Responsables de avisos",
        domain="[(\'company_ids\', \'in\', [id])]",
        help="Usuarios que recibirán actividades internas de seguimiento.",
    )
    co_dian_certificate_subject = fields.Char(string="Titular del certificado", readonly=True, copy=False)
    co_dian_certificate_issuer = fields.Char(string="Emisor del certificado", readonly=True, copy=False)
    co_dian_certificate_serial = fields.Char(string="Serial del certificado", readonly=True, copy=False)
    co_dian_certificate_expiration = fields.Datetime(string="Vencimiento del certificado", readonly=True, copy=False)
    co_dian_certificate_fingerprint = fields.Char(string="Huella SHA-256", readonly=True, copy=False)
    co_dian_certificate_status = fields.Selection([
        ("valid", "Válido"), ("expiring", "Próximo a vencer"), ("expired", "Vencido"), ("invalid", "Inválido"), ("missing", "Sin certificado"),
    ], string="Estado certificado", readonly=True, copy=False)
    co_dian_test_payroll_count = fields.Integer(string="Nóminas de habilitación aceptadas", compute="_compute_co_dian_habilitation")
    co_dian_test_adjustment_count = fields.Integer(string="Ajustes de habilitación aceptados", compute="_compute_co_dian_habilitation")
    co_dian_habilitation_ready = fields.Boolean(string="Habilitación mínima completada", compute="_compute_co_dian_habilitation")

    co_dian_document_count = fields.Integer(string="Documentos DIAN", compute="_compute_co_dian_metrics")
    co_dian_accepted_count = fields.Integer(string="Aceptados DIAN", compute="_compute_co_dian_metrics")
    co_dian_pending_count = fields.Integer(string="Pendientes DIAN", compute="_compute_co_dian_metrics")
    co_dian_rejected_count = fields.Integer(string="Rechazados DIAN", compute="_compute_co_dian_metrics")
    co_dian_error_count = fields.Integer(string="Errores DIAN", compute="_compute_co_dian_metrics")

    def _compute_co_dian_habilitation(self):
        document_model = self.env["l10n.co.payroll.dian.document"]
        for company in self:
            accepted = document_model.search([("company_id", "=", company.id), ("state", "=", "accepted"), ("submission_environment", "=", "2")])
            company.co_dian_test_payroll_count = len(accepted.filtered(lambda document: not document.is_adjustment))
            company.co_dian_test_adjustment_count = len(accepted.filtered("is_adjustment"))
            company.co_dian_habilitation_ready = company.co_dian_test_payroll_count >= 4 and company.co_dian_test_adjustment_count >= 4

    def _compute_co_dian_metrics(self):
        document_model = self.env["l10n.co.payroll.dian.document"]
        for company in self:
            documents = document_model.search([("company_id", "=", company.id)])
            company.co_dian_document_count = len(documents)
            company.co_dian_accepted_count = len(documents.filtered(lambda record: record.state == "accepted"))
            company.co_dian_pending_count = len(documents.filtered(lambda record: record.state == "pending"))
            company.co_dian_rejected_count = len(documents.filtered(lambda record: record.state == "rejected"))
            company.co_dian_error_count = len(documents.filtered(lambda record: record.state == "error"))

    def action_open_co_dian_dashboard(self):
        self.ensure_one()
        dashboard = self.env["l10n.co.payroll.dian.dashboard"].create({"company_id": self.id})
        return {
            "type": "ir.actions.act_window",
            "name": _("Panel DIAN"),
            "res_model": "l10n.co.payroll.dian.dashboard",
            "view_mode": "form",
            "res_id": dashboard.id,
            "target": "current",
        }

    def action_open_co_dian_setup(self):
        self.ensure_one()
        wizard = self.env["l10n.co.payroll.dian.setup.wizard"].with_context(
            default_company_id=self.id,
        ).create({"company_id": self.id})
        return {
            "type": "ir.actions.act_window",
            "name": _("Asistente de configuración DIAN"),
            "res_model": "l10n.co.payroll.dian.setup.wizard",
            "view_mode": "form",
            "res_id": wizard.id,
            "target": "new",
        }

    def action_co_dian_validate_configuration(self):
        for company in self:
            errors = []
            if not company.vat:
                errors.append(_("Configura el NIT de la compañía."))
            if not company.co_dian_software_id:
                errors.append(_("Configura el ID del software DIAN."))
            if not company.co_dian_software_pin:
                errors.append(_("Configura el PIN del software DIAN."))
            if company.co_dian_environment == "2" and not company.co_dian_test_set_id:
                errors.append(_("Configura el Test Set ID para habilitación."))
            if company.co_dian_max_retries < 0:
                errors.append(_("El máximo de reintentos no puede ser negativo."))
            if company.co_dian_retry_delay_minutes < 1:
                errors.append(_("La espera entre reintentos debe ser de al menos un minuto."))
            if company.co_dian_pending_alert_hours < 1:
                errors.append(_("Las horas para alertar pendientes deben ser mayores que cero."))
            if errors:
                raise UserError("\n".join(errors))
        return {"type": "ir.actions.client", "tag": "display_notification", "params": {
            "title": _("Configuración DIAN válida"),
            "message": _("Los datos básicos de la compañía están completos."),
            "type": "success", "sticky": False,
        }}

    @api.model
    def _cron_create_dian_notifications(self):
        document_model = self.env["l10n.co.payroll.dian.document"]
        activity_type = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
        if not activity_type:
            return True
        company_model_id = self.env["ir.model"]._get_id("res.company")
        document_model_id = self.env["ir.model"]._get_id("l10n.co.payroll.dian.document")
        now = fields.Datetime.now()
        for company in self.search([("co_dian_notifications_enabled", "=", True)]):
            users = company.co_dian_notify_user_ids or self.env["res.users"].search([
                ("company_ids", "in", company.id), ("all_group_ids", "in", self.env.ref("l10n_co_payroll.group_co_payroll_manager").id),
            ], limit=5)
            if not users:
                users = self.env.user
            if company.co_dian_notify_errors:
                documents = document_model.search([("company_id", "=", company.id), ("state", "=", "error")], limit=100)
                for document in documents:
                    self._create_dian_activity(document, document_model_id, users, activity_type, _("Error DIAN: %s") % (document.name or document.employee_id.display_name), document.error_message or document.status_message or _("Revisar el documento."))
            if company.co_dian_notify_pending:
                threshold = now - timedelta(hours=max(company.co_dian_pending_alert_hours, 1))
                documents = document_model.search([("company_id", "=", company.id), ("state", "=", "pending"), ("sent_at", "<=", threshold)], limit=100)
                for document in documents:
                    self._create_dian_activity(document, document_model_id, users, activity_type, _("Pendiente DIAN: %s") % (document.name or document.employee_id.display_name), _("El documento lleva más de %s horas sin respuesta.") % company.co_dian_pending_alert_hours)
            if company.co_dian_notify_certificate and company.co_dian_certificate_status in ("expiring", "expired"):
                message = _("El certificado DIAN está vencido.") if company.co_dian_certificate_status == "expired" else _("El certificado DIAN está próximo a vencer el %s.") % fields.Datetime.to_string(company.co_dian_certificate_expiration)
                self._create_dian_activity(company, company_model_id, users, activity_type, _("Revisar certificado DIAN"), message)
        return True

    @staticmethod
    def _create_dian_activity(record, model_id, users, activity_type, summary, note):
        activity_model = record.env["mail.activity"]
        for user in users:
            existing = activity_model.search([
                ("res_model_id", "=", model_id), ("res_id", "=", record.id),
                ("user_id", "=", user.id), ("summary", "=", summary), ("active", "=", True),
            ], limit=1)
            if not existing:
                activity_model.create({
                    "activity_type_id": activity_type.id, "res_model_id": model_id, "res_id": record.id,
                    "user_id": user.id, "summary": summary, "note": note,
                })

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
            now = fields.Datetime.now()
            alert_limit = now + timedelta(days=max(company.co_dian_certificate_alert_days, 0))
            status = "expired" if expiration < now else ("expiring" if expiration <= alert_limit else "valid")
            company.write({
                "co_dian_certificate_subject": certificate.subject.rfc4514_string(),
                "co_dian_certificate_issuer": certificate.issuer.rfc4514_string(),
                "co_dian_certificate_serial": str(certificate.serial_number),
                "co_dian_certificate_expiration": fields.Datetime.to_string(expiration),
                "co_dian_certificate_fingerprint": certificate.fingerprint(hashes.SHA256()).hex(),
                "co_dian_certificate_status": status,
            })
        status = self[:1].co_dian_certificate_status
        return {"type": "ir.actions.client", "tag": "display_notification", "params": {
            "title": _("Certificado próximo a vencer") if status == "expiring" else (_("Certificado vencido") if status == "expired" else _("Certificado válido")),
            "message": _("Renueva el certificado antes de transmitir nuevos documentos.") if status in ("expiring", "expired") else _("El material de firma se puede utilizar para firmar XML y autenticar SOAP."),
            "type": "warning" if status in ("expiring", "expired") else "success",
            "sticky": status in ("expiring", "expired"),
        }}

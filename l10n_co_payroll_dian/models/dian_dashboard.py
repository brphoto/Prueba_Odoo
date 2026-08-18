from odoo import _, api, fields, models


class CoPayrollDianDashboard(models.TransientModel):
    _name = "l10n.co.payroll.dian.dashboard"
    _description = "Panel operativo de nómina electrónica DIAN"

    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    date_from = fields.Date(string="Desde")
    date_to = fields.Date(string="Hasta")
    total_count = fields.Integer(string="Total", compute="_compute_metrics")
    accepted_count = fields.Integer(string="Aceptados", compute="_compute_metrics")
    pending_count = fields.Integer(string="Pendientes", compute="_compute_metrics")
    rejected_count = fields.Integer(string="Rechazados", compute="_compute_metrics")
    error_count = fields.Integer(string="Errores", compute="_compute_metrics")
    attention_count = fields.Integer(string="Requieren atención", compute="_compute_metrics")
    stale_pending_count = fields.Integer(string="Pendientes antiguos", compute="_compute_metrics")
    habilitation_payroll_count = fields.Integer(string="Nóminas de habilitación", related="company_id.co_dian_test_payroll_count")
    habilitation_adjustment_count = fields.Integer(string="Ajustes de habilitación", related="company_id.co_dian_test_adjustment_count")
    habilitation_ready = fields.Boolean(string="Habilitación lista", related="company_id.co_dian_habilitation_ready")
    certificate_status = fields.Selection(related="company_id.co_dian_certificate_status")
    certificate_expiration = fields.Datetime(related="company_id.co_dian_certificate_expiration")
    environment = fields.Selection(related="company_id.co_dian_environment")
    last_sync = fields.Datetime(string="Última consulta", compute="_compute_metrics")

    @api.depends("company_id", "date_from", "date_to")
    def _compute_metrics(self):
        document_model = self.env["l10n.co.payroll.dian.document"]
        for dashboard in self:
            domain = [("company_id", "=", dashboard.company_id.id)]
            if dashboard.date_from:
                domain.append(("period_id.date_to", ">=", dashboard.date_from))
            if dashboard.date_to:
                domain.append(("period_id.date_from", "<=", dashboard.date_to))
            documents = document_model.search(domain)
            dashboard.total_count = len(documents)
            dashboard.accepted_count = len(documents.filtered(lambda record: record.state == "accepted"))
            dashboard.pending_count = len(documents.filtered(lambda record: record.state == "pending"))
            dashboard.rejected_count = len(documents.filtered(lambda record: record.state == "rejected"))
            dashboard.error_count = len(documents.filtered(lambda record: record.state == "error"))
            dashboard.attention_count = len(documents.filtered(lambda record: record.attention_level in ("warning", "danger")))
            dashboard.stale_pending_count = len(documents.filtered("is_stale_pending"))
            checked = [value for value in documents.mapped("last_checked_at") if value]
            dashboard.last_sync = max(checked) if checked else False

    def _document_domain(self, state=False):
        self.ensure_one()
        domain = [("company_id", "=", self.company_id.id)]
        if state:
            domain.append(("state", "=", state))
        if self.date_from:
            domain.append(("period_id.date_to", ">=", self.date_from))
        if self.date_to:
            domain.append(("period_id.date_from", "<=", self.date_to))
        return domain

    def action_open_documents(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Documentos DIAN"),
            "res_model": "l10n.co.payroll.dian.document",
            "view_mode": "list,form",
            "domain": self._document_domain(),
        }

    def action_open_accepted(self):
        self.ensure_one()
        action = self.action_open_documents()
        action["domain"] = self._document_domain("accepted")
        return action

    def action_open_pending(self):
        self.ensure_one()
        action = self.action_open_documents()
        action["domain"] = self._document_domain("pending")
        return action

    def action_open_errors(self):
        self.ensure_one()
        action = self.action_open_documents()
        action["domain"] = self._document_domain("error")
        return action

    def action_open_attention(self):
        self.ensure_one()
        action = self.action_open_documents()
        action["domain"] = self._document_domain() + [("attention_level", "in", ["warning", "danger"])]
        return action

    def action_refresh(self):
        return {"type": "ir.actions.client", "tag": "soft_reload"}


class CoPayrollDianSetupWizard(models.TransientModel):
    _name = "l10n.co.payroll.dian.setup.wizard"
    _description = "Asistente de configuración DIAN"

    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    enabled = fields.Boolean(string="Activar nómina electrónica", default=True)
    environment = fields.Selection([("1", "Producción"), ("2", "Habilitación")], string="Ambiente", required=True)
    software_id = fields.Char(string="ID del software")
    software_pin = fields.Char(string="PIN del software")
    test_set_id = fields.Char(string="Test Set ID")
    certificate = fields.Binary(string="Certificado PKCS#12")
    certificate_filename = fields.Char(string="Nombre del certificado")
    certificate_password = fields.Char(string="Contraseña del certificado")
    native_certificate_id = fields.Many2one("certificate.certificate", string="Certificado nativo Odoo")
    auto_check = fields.Boolean(string="Consultar pendientes automáticamente", default=False)
    require_habilitation = fields.Boolean(string="Exigir habilitación antes de producción", default=False)
    require_explicit_mapping = fields.Boolean(string="Exigir mapeo DIAN explícito", default=False)
    approval_mode = fields.Selection([
        ("none", "Sin aprobación"), ("single", "Una aprobación"), ("double", "Doble aprobación"),
    ], string="Aprobación de envío", required=True, default="none")
    notifications_enabled = fields.Boolean(string="Avisos operativos", default=True)
    notify_errors = fields.Boolean(string="Avisar errores", default=True)
    notify_pending = fields.Boolean(string="Avisar pendientes antiguos", default=True)
    pending_alert_hours = fields.Integer(string="Horas para alertar pendientes", default=4)
    notify_certificate = fields.Boolean(string="Avisar certificado", default=True)
    notify_user_ids = fields.Many2many("res.users", string="Responsables de avisos")

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        company = self.env.company
        values.update({
            "enabled": company.co_dian_payroll_enabled,
            "environment": company.co_dian_environment or "2",
            "software_id": company.co_dian_software_id,
            "software_pin": company.co_dian_software_pin,
            "test_set_id": company.co_dian_test_set_id,
            "certificate": company.co_dian_certificate,
            "certificate_filename": company.co_dian_certificate_filename,
            "certificate_password": company.co_dian_certificate_password,
            "native_certificate_id": company.co_dian_certificate_id.id,
            "auto_check": company.co_dian_auto_check_pending,
            "require_habilitation": company.co_dian_require_habilitation,
            "require_explicit_mapping": company.co_dian_require_explicit_mapping,
            "approval_mode": company.co_dian_approval_mode,
            "notifications_enabled": company.co_dian_notifications_enabled,
            "notify_errors": company.co_dian_notify_errors,
            "notify_pending": company.co_dian_notify_pending,
            "pending_alert_hours": company.co_dian_pending_alert_hours,
            "notify_certificate": company.co_dian_notify_certificate,
            "notify_user_ids": [(6, 0, company.co_dian_notify_user_ids.ids)],
        })
        return values

    def _values(self):
        self.ensure_one()
        return {
            "co_dian_payroll_enabled": self.enabled,
            "co_dian_environment": self.environment,
            "co_dian_software_id": self.software_id,
            "co_dian_software_pin": self.software_pin,
            "co_dian_test_set_id": self.test_set_id,
            "co_dian_certificate": self.certificate,
            "co_dian_certificate_filename": self.certificate_filename,
            "co_dian_certificate_password": self.certificate_password,
            "co_dian_certificate_id": self.native_certificate_id.id,
            "co_dian_auto_check_pending": self.auto_check,
            "co_dian_require_habilitation": self.require_habilitation,
            "co_dian_require_explicit_mapping": self.require_explicit_mapping,
            "co_dian_approval_mode": self.approval_mode,
            "co_dian_notifications_enabled": self.notifications_enabled,
            "co_dian_notify_errors": self.notify_errors,
            "co_dian_notify_pending": self.notify_pending,
            "co_dian_pending_alert_hours": self.pending_alert_hours,
            "co_dian_notify_certificate": self.notify_certificate,
            "co_dian_notify_user_ids": [(6, 0, self.notify_user_ids.ids)],
        }

    def action_apply(self):
        self.ensure_one()
        self.company_id.write(self._values())
        return {"type": "ir.actions.client", "tag": "display_notification", "params": {
            "title": _("Configuración guardada"),
            "message": _("La configuración DIAN quedó actualizada."),
            "type": "success", "sticky": False,
        }}

    def action_apply_and_validate(self):
        self.ensure_one()
        self.company_id.write(self._values())
        self.company_id.action_co_dian_validate_configuration()
        if self.company_id._co_dian_signing_material():
            self.company_id.action_co_dian_validate_certificate()
        return {"type": "ir.actions.client", "tag": "display_notification", "params": {
            "title": _("Configuración válida"),
            "message": _("La configuración y el certificado están listos para las validaciones locales."),
            "type": "success", "sticky": False,
        }}

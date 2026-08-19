from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CoPayrollDianPeriod(models.Model):
    _inherit = "l10n.co.payroll.period"

    dian_document_ids = fields.One2many("l10n.co.payroll.dian.document", "period_id", string="Documentos DIAN", copy=False)
    dian_document_count = fields.Integer(string="Cantidad de documentos DIAN", compute="_compute_dian_metrics")
    dian_pending_count = fields.Integer(string="Pendientes DIAN", compute="_compute_dian_metrics")
    dian_rejected_count = fields.Integer(string="Rechazados DIAN", compute="_compute_dian_metrics")
    dian_attention_count = fields.Integer(string="Requieren atención DIAN", compute="_compute_dian_metrics")
    dian_state = fields.Selection([
        ("none", "Sin generar"), ("draft", "Borrador"), ("generated", "Generados"),
        ("pending", "Pendientes"), ("accepted", "Aceptados"), ("rejected", "Con rechazos"),
    ], compute="_compute_dian_metrics", string="Estado DIAN")
    dian_due_date = fields.Date(string="Vencimiento nómina electrónica", compute="_compute_dian_due_date", store=True,
        help="Primeros diez días calendario del mes siguiente al periodo, según la regla parametrizada para nómina electrónica.")
    dian_days_remaining = fields.Integer(string="Días para vencimiento DIAN", compute="_compute_dian_deadline_status")
    dian_deadline_state = fields.Selection([
        ("ok", "En plazo"), ("soon", "Próximo a vencer"), ("overdue", "Vencido"),
    ], string="Estado de vencimiento DIAN", compute="_compute_dian_deadline_status")

    @api.depends("date_to")
    def _compute_dian_due_date(self):
        today = fields.Date.context_today(self)
        for period in self:
            due_date = period.date_to + relativedelta(day=1, months=1, days=9) if period.date_to else False
            period.dian_due_date = due_date
            period.dian_days_remaining = 0
            period.dian_deadline_state = "ok"

    @api.depends("dian_due_date")
    def _compute_dian_deadline_status(self):
        today = fields.Date.context_today(self)
        for period in self:
            due_date = period.dian_due_date
            period.dian_days_remaining = (due_date - today).days if due_date else 0
            period.dian_deadline_state = "overdue" if due_date and due_date < today else ("soon" if due_date and (due_date - today).days <= 3 else "ok")

    @api.depends("dian_document_ids.state")
    def _compute_dian_metrics(self):
        for period in self:
            documents = period.dian_document_ids
            period.dian_document_count = len(documents)
            period.dian_pending_count = len(documents.filtered(lambda doc: doc.state == "pending"))
            period.dian_rejected_count = len(documents.filtered(lambda doc: doc.state in ("rejected", "error")))
            period.dian_attention_count = len(documents.filtered(lambda doc: doc.attention_level in ("warning", "danger")))
            if not documents:
                period.dian_state = "none"
            elif period.dian_rejected_count:
                period.dian_state = "rejected"
            elif documents.filtered(lambda doc: doc.state == "pending"):
                period.dian_state = "pending"
            elif all(doc.state == "accepted" for doc in documents):
                period.dian_state = "accepted"
            elif documents.filtered(lambda doc: doc.state in ("generated", "validated")):
                period.dian_state = "generated"
            else:
                period.dian_state = "draft"

    def action_generate_dian_documents(self):
        document_model = self.env["l10n.co.payroll.dian.document"]
        for period in self:
            if period.state not in ("ready", "closed"):
                raise UserError(_("El periodo debe estar preparado o cerrado antes de generar nómina electrónica."))
            if not period.company_id.co_dian_payroll_enabled:
                raise UserError(_("Activa nómina electrónica DIAN en la compañía %s.") % period.company_id.display_name)
            existing = period.dian_document_ids.filtered(lambda doc: not doc.is_adjustment)
            for line in period.line_ids:
                if not existing.filtered(lambda doc, line=line: doc.period_line_id == line):
                    document_model.create({"period_id": period.id, "period_line_id": line.id, "company_id": period.company_id.id})
            period.dian_document_ids.filtered(lambda doc: doc.state in ("draft", "error") and not doc.is_adjustment).action_generate()
        return {"type": "ir.actions.client", "tag": "soft_reload"}


class CoPayrollDianPeriodActions(models.Model):
    _inherit = "l10n.co.payroll.period"

    def action_send_dian_documents(self):
        for period in self:
            documents = period.dian_document_ids.filtered(lambda doc: not doc.is_adjustment and doc.state in ("validated", "generated"))
            if not documents:
                raise UserError(_("No hay documentos DIAN validados localmente para enviar."))
            documents.action_send()
        return {"type": "ir.actions.client", "tag": "soft_reload"}

    def action_prevalidate_dian_documents(self):
        for period in self:
            documents = period.dian_document_ids.filtered(lambda doc: not doc.is_adjustment and doc.state in ("draft", "error", "validated", "generated"))
            if not documents:
                raise UserError(_("No hay documentos DIAN disponibles para prevalidar."))
            documents.action_prevalidate()
        return {"type": "ir.actions.client", "tag": "soft_reload"}

    def action_approve_dian_documents(self):
        for period in self:
            documents = period.dian_document_ids.filtered(lambda doc: doc.state in ("validated", "generated") and doc.company_id.co_dian_approval_mode != "none")
            if not documents:
                raise UserError(_("No hay documentos que requieran aprobación DIAN."))
            documents.action_approve_send()
        return {"type": "ir.actions.client", "tag": "soft_reload"}

    def action_export_dian_csv(self):
        self.ensure_one()
        documents = self.dian_document_ids
        if not documents:
            raise UserError(_("El periodo no tiene documentos DIAN."))
        return documents.action_export_csv()

    def action_check_dian_status(self):
        for period in self:
            period.dian_document_ids.filtered(lambda doc: doc.state == "pending" and (doc.zip_key or doc.cune)).action_check_status()
        return {"type": "ir.actions.client", "tag": "soft_reload"}

    def action_open_dian_documents(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": _("Nómina electrónica DIAN"), "res_model": "l10n.co.payroll.dian.document", "view_mode": "list,form", "domain": [("period_id", "=", self.id)], "context": {"default_period_id": self.id, "create": False}}


class CoPayrollDianPeriodLine(models.Model):
    _inherit = "l10n.co.payroll.period.line"

    dian_document_ids = fields.One2many(
        "l10n.co.payroll.dian.document",
        "period_line_id",
        string="Documentos DIAN del consolidado",
        readonly=True,
    )
    dian_document_count = fields.Integer(string="Documentos DIAN", compute="_compute_dian_line_metrics")
    dian_document_id = fields.Many2one(
        "l10n.co.payroll.dian.document",
        string="Documento DIAN consolidado",
        compute="_compute_dian_line_metrics",
    )

    @api.depends("dian_document_ids", "dian_document_ids.is_adjustment", "dian_document_ids.state")
    def _compute_dian_line_metrics(self):
        for line in self:
            documents = line.dian_document_ids.filtered(lambda doc: not doc.is_adjustment)
            line.dian_document_count = len(documents)
            line.dian_document_id = documents.sorted(key=lambda doc: doc.id, reverse=True)[:1].id if documents else False

    def action_open_dian_document(self):
        self.ensure_one()
        document = self.dian_document_id
        if not document:
            raise UserError(_("Este consolidado todavía no tiene documento DIAN."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Documento DIAN consolidado"),
            "res_model": "l10n.co.payroll.dian.document",
            "view_mode": "form",
            "res_id": document.id,
        }

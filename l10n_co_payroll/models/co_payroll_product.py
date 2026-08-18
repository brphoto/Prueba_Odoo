from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CoPayrollBankFormat(models.Model):
    _name = "l10n.co.payroll.bank.format"
    _description = "Formato bancario de pagos de nómina"
    _order = "company_id, name"
    _check_company_auto = True

    name = fields.Char(string="Nombre", required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    operator = fields.Selection([
        ("generic", "Archivo genérico"),
        ("ach", "ACH / multibanco"),
        ("bancolombia", "Bancolombia"),
        ("davivienda", "Davivienda"),
        ("bogota", "Banco de Bogotá"),
        ("other", "Otro operador"),
    ], string="Operador", required=True, default="generic")
    delimiter = fields.Char(string="Separador", required=True, default=";")
    encoding = fields.Selection([
        ("utf-8-sig", "UTF-8 con BOM"), ("cp1252", "ANSI / Windows-1252"),
    ], string="Codificación", required=True, default="utf-8-sig")
    include_header = fields.Boolean(string="Incluir encabezado", default=True)
    line_ending = fields.Selection([("crlf", "Windows (CRLF)"), ("lf", "Unix (LF)")], string="Fin de línea", default="crlf", required=True)
    filename_prefix = fields.Char(string="Prefijo de archivo", default="PAGOS_NOMINA")
    active = fields.Boolean(default=True)
    technical_reference = fields.Text(string="Referencia técnica", help="Documenta la versión del formato acordada con el banco u operador.")

    _company_name_unique = models.Constraint("unique(company_id, name)", "Ya existe un formato bancario con este nombre.")

    @api.model
    def get_default(self, company):
        return self.search([("company_id", "=", company.id), ("active", "=", True)], order="id", limit=1)


class CoPayrollPeriodProduct(models.Model):
    _inherit = "l10n.co.payroll.period"

    workflow_stage = fields.Selection([
        ("draft", "Pendiente de preparar"),
        ("review", "Revisar excepciones"),
        ("ready", "Listo para cierre"),
        ("closed", "Cerrado"),
        ("cancelled", "Cancelado"),
    ], string="Etapa operativa", compute="_compute_workflow_stage")

    @api.depends("state", "diagnostic_ids.severity", "diagnostic_ids.resolved", "blocking_issue_count")
    def _compute_workflow_stage(self):
        for period in self:
            if period.state == "draft":
                stage = "draft"
            elif period.state == "closed":
                stage = "closed"
            elif period.state == "cancelled":
                stage = "cancelled"
            elif period.blocking_issue_count or period.diagnostic_error_count:
                stage = "review"
            else:
                stage = "ready"
            period.workflow_stage = stage

    def action_prepare_and_validate(self):
        for period in self:
            if period.state == "draft":
                period.action_prepare()
            if period.state == "ready":
                period.action_run_checks()
        return self._reload_form()

    def action_create_payment_batch(self):
        self.ensure_one()
        if self.state not in ("ready", "closed"):
            raise UserError(_("Prepara y valida el periodo antes de crear el lote de pagos."))
        batch = self.env["l10n.co.payroll.payment.batch"].search([("period_id", "=", self.id), ("state", "!=", "cancelled")], limit=1)
        if not batch:
            batch = self.env["l10n.co.payroll.payment.batch"].create({
                "name": _("Pago - %s") % self.name,
                "company_id": self.company_id.id,
                "period_id": self.id,
                "payment_date": self.payment_date or self.date_to,
            })
        return {"type": "ir.actions.act_window", "name": _("Lote de pagos"), "res_model": batch._name, "view_mode": "form", "res_id": batch.id}

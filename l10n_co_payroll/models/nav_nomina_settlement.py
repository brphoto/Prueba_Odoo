from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class NavNominaSettlement(models.Model):
    _name = "nav.nomina.settlement"
    _description = "Liquidación definitiva de nómina"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "termination_date desc, id desc"
    _check_company_auto = True

    name = fields.Char(string="Referencia", required=True, copy=False, default=lambda self: _("Liquidación"), tracking=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    employee_id = fields.Many2one("hr.employee", required=True, index=True, tracking=True)
    period_id = fields.Many2one("nav.nomina.period", string="Periodo de salida", ondelete="restrict")
    termination_date = fields.Date(string="Fecha de retiro", required=True, default=fields.Date.context_today, tracking=True)
    reason = fields.Selection([("resignation", "Renuncia"), ("dismissal", "Terminación"), ("mutual", "Mutuo acuerdo"), ("retirement", "Pensión"), ("other", "Otro")], string="Motivo", required=True, default="other")
    base_salary = fields.Monetary(string="Salario base", required=True, currency_field="currency_id")
    service_days = fields.Float(string="Días de servicio")
    pending_wages = fields.Monetary(string="Salarios pendientes", currency_field="currency_id")
    severance = fields.Monetary(string="Cesantías", currency_field="currency_id")
    severance_interest = fields.Monetary(string="Intereses de cesantías", currency_field="currency_id")
    vacation = fields.Monetary(string="Vacaciones", currency_field="currency_id")
    bonus = fields.Monetary(string="Prima proporcional", currency_field="currency_id")
    deductions = fields.Monetary(string="Descuentos", currency_field="currency_id")
    total = fields.Monetary(string="Total liquidación", compute="_compute_total", store=True, currency_field="currency_id")
    state = fields.Selection([("draft", "Borrador"), ("calculated", "Calculada"), ("approved", "Aprobada"), ("paid", "Pagada"), ("cancelled", "Cancelada")], default="draft", required=True, tracking=True)
    calculated_by = fields.Many2one("res.users", readonly=True, copy=False)
    calculated_at = fields.Datetime(readonly=True, copy=False)
    approved_by = fields.Many2one("res.users", readonly=True, copy=False)
    approved_at = fields.Datetime(readonly=True, copy=False)
    notes = fields.Text(string="Observaciones")
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)

    @api.depends("pending_wages", "severance", "severance_interest", "vacation", "bonus", "deductions")
    def _compute_total(self):
        for record in self:
            record.total = sum([record.pending_wages, record.severance, record.severance_interest, record.vacation, record.bonus]) - record.deductions

    @api.constrains("base_salary", "service_days", "termination_date")
    def _check_values(self):
        for record in self:
            if record.base_salary < 0 or record.service_days < 0:
                raise ValidationError(_("El salario base y los días de servicio no pueden ser negativos."))

    def action_calculate(self):
        for record in self:
            if record.state not in ("draft", "calculated"):
                raise UserError(_("La liquidación ya está aprobada, pagada o cancelada."))
            record.write({"state": "calculated", "calculated_by": self.env.user.id, "calculated_at": fields.Datetime.now()})
        return True

    def action_approve(self):
        if not (self.env.su or self.env.user._is_admin() or self.env.user.has_group("l10n_co_payroll.group_nav_nomina_manager")):
            raise UserError(_("Solo un supervisor puede aprobar liquidaciones."))
        for record in self:
            if record.state != "calculated":
                raise UserError(_("Calcula la liquidación antes de aprobarla."))
            record.write({"state": "approved", "approved_by": self.env.user.id, "approved_at": fields.Datetime.now()})
            self.env["nav.nomina.audit"].sudo().create({"company_id": record.company_id.id, "period_id": record.period_id.id if record.period_id else False, "res_model": record._name, "res_id": record.id, "action": "settlement", "description": _("Liquidación aprobada por %s.") % self.env.user.name})
        return True

    def action_mark_paid(self):
        if not (self.env.su or self.env.user._is_admin() or self.env.user.has_group("l10n_co_payroll.group_nav_nomina_manager")):
            raise UserError(_("Solo un supervisor puede marcar liquidaciones como pagadas."))
        self.filtered(lambda record: record.state == "approved").write({"state": "paid"})
        return True

    def action_cancel(self):
        self.write({"state": "cancelled"})
        return True

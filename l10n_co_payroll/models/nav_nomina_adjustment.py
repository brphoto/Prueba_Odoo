from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class NavNominaAdjustment(models.Model):
    _name = "nav.nomina.adjustment"
    _description = "Ajuste y descuento de nómina"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"
    _check_company_auto = True

    name = fields.Char(string="Referencia", required=True, copy=False, default=lambda self: _("Ajuste"), tracking=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    employee_id = fields.Many2one("hr.employee", required=True, index=True, tracking=True)
    period_id = fields.Many2one("nav.nomina.period", string="Periodo destino", ondelete="restrict", index=True)
    adjustment_type = fields.Selection([
        ("retroactive", "Retroactivo"), ("advance", "Anticipo"), ("loan", "Préstamo"),
        ("embargo", "Embargo"), ("other", "Otro"),
    ], string="Tipo", required=True, default="other", tracking=True)
    date = fields.Date(string="Fecha", required=True, default=fields.Date.context_today, index=True)
    amount = fields.Monetary(string="Valor total", required=True, currency_field="currency_id")
    installment_amount = fields.Monetary(string="Cuota", currency_field="currency_id")
    installments = fields.Integer(string="Número de cuotas", default=1)
    installment_number = fields.Integer(string="Cuota actual", default=1)
    state = fields.Selection([("draft", "Borrador"), ("approved", "Aprobado"), ("applied", "Aplicado"), ("rejected", "Rechazado")], default="draft", required=True, tracking=True)
    approved_by = fields.Many2one("res.users", readonly=True, copy=False)
    approved_at = fields.Datetime(readonly=True, copy=False)
    applied_at = fields.Datetime(readonly=True, copy=False)
    notes = fields.Text(string="Soporte / observaciones")
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)

    @api.constrains("amount", "installments", "installment_number", "employee_id", "company_id")
    def _check_values(self):
        for record in self:
            if record.amount <= 0:
                raise ValidationError(_("El valor del ajuste debe ser mayor que cero."))
            if record.installments < 1 or record.installment_number < 1 or record.installment_number > record.installments:
                raise ValidationError(_("La cuota actual debe estar entre 1 y el número de cuotas."))
            if record.employee_id.company_id and record.employee_id.company_id != record.company_id:
                raise ValidationError(_("El empleado debe pertenecer a la compañía del ajuste."))

    def action_approve(self):
        if not (self.env.su or self.env.user._is_admin() or self.env.user.has_group("l10n_co_payroll.group_nav_nomina_manager")):
            raise UserError(_("Solo un supervisor puede aprobar ajustes."))
        self.write({"state": "approved", "approved_by": self.env.user.id, "approved_at": fields.Datetime.now()})
        return True

    def action_reject(self):
        if not (self.env.su or self.env.user._is_admin() or self.env.user.has_group("l10n_co_payroll.group_nav_nomina_manager")):
            raise UserError(_("Solo un supervisor puede rechazar ajustes."))
        self.write({"state": "rejected"})
        return True

    def action_apply(self):
        for record in self:
            if record.state != "approved":
                raise UserError(_("Solo puedes aplicar ajustes aprobados."))
            if record.period_id and record.period_id.state == "closed":
                raise UserError(_("No puedes aplicar ajustes en un periodo cerrado."))
            record.write({"state": "applied", "applied_at": fields.Datetime.now()})
            if record.period_id:
                self.env["nav.nomina.audit"].sudo().create({"company_id": record.company_id.id, "period_id": record.period_id.id, "res_model": record._name, "res_id": record.id, "action": "other", "description": _("Ajuste %s aplicado: %s.") % (record.adjustment_type, record.amount)})
        return True

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class NavNominaNovelty(models.Model):
    _name = "nav.nomina.novelty"
    _description = "Novedad laboral de nómina"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_from, employee_id"
    _check_company_auto = True

    name = fields.Char(string="Referencia", required=True, copy=False, default=lambda self: _("Novedad"), tracking=True)
    company_id = fields.Many2one(related="period_id.company_id", store=True, readonly=True)
    period_id = fields.Many2one("nav.nomina.period", string="Periodo", required=True, ondelete="cascade", index=True, tracking=True)
    employee_id = fields.Many2one("hr.employee", string="Empleado", required=True, index=True, tracking=True)
    novelty_type = fields.Selection([
        ("ing", "ING - Ingreso"), ("ret", "RET - Retiro"), ("vsp", "VSP - Variación permanente"),
        ("vst", "VST - Variación transitoria"), ("sln", "SLN - Suspensión/licencia no remunerada"),
        ("ige", "IGE - Incapacidad enfermedad general"), ("lma", "LMA - Licencia maternidad/paternidad"),
        ("vac", "VAC-LR - Vacaciones/licencia remunerada"), ("irl", "IRL - Accidente/enfermedad laboral"),
        ("vct", "VCT - Variación centro de trabajo"),
    ], string="Tipo de novedad", required=True, tracking=True)
    date_from = fields.Date(string="Desde", required=True, tracking=True)
    date_to = fields.Date(string="Hasta", required=True, tracking=True)
    days = fields.Float(string="Días", required=True, default=0.0)
    amount = fields.Monetary(string="Valor asociado", currency_field="currency_id")
    affects_ibc = fields.Boolean(string="Afecta IBC", default=True)
    state = fields.Selection([
        ("draft", "Pendiente"), ("approved", "Aprobada"), ("applied", "Aplicada"), ("rejected", "Rechazada")
    ], string="Estado", default="draft", required=True, tracking=True)
    approved_by = fields.Many2one("res.users", string="Aprobada por", readonly=True, copy=False)
    approved_at = fields.Datetime(string="Fecha de aprobación", readonly=True, copy=False)
    notes = fields.Text(string="Observaciones")
    currency_id = fields.Many2one(related="period_id.currency_id", readonly=True)

    @api.constrains("date_from", "date_to", "days")
    def _check_dates_and_days(self):
        for novelty in self:
            if novelty.period_id and novelty.period_id.state in ("closed", "cancelled"):
                raise ValidationError(_("No puedes registrar o modificar novedades de un periodo cerrado o cancelado."))
            if novelty.date_from and novelty.date_to and novelty.date_from > novelty.date_to:
                raise ValidationError(_("La fecha inicial de la novedad no puede ser posterior a la fecha final."))
            if novelty.days < 0:
                raise ValidationError(_("Los días de una novedad no pueden ser negativos."))
            if novelty.period_id and novelty.date_from and novelty.date_to:
                if novelty.date_from < novelty.period_id.date_from or novelty.date_to > novelty.period_id.date_to:
                    raise ValidationError(_("La novedad debe estar dentro del periodo seleccionado."))

    def action_approve(self):
        if not (self.env.su or self.env.user._is_admin() or self.env.user.has_group("l10n_co_payroll.group_nav_nomina_manager")):
            raise UserError(_("Solo un supervisor puede aprobar novedades."))
        if any(novelty.period_id.state in ("closed", "cancelled") for novelty in self):
            raise UserError(_("No puedes aprobar novedades de un periodo cerrado o cancelado."))
        self.write({"state": "approved", "approved_by": self.env.user.id, "approved_at": fields.Datetime.now()})

    def action_reject(self):
        if not (self.env.su or self.env.user._is_admin() or self.env.user.has_group("l10n_co_payroll.group_nav_nomina_manager")):
            raise UserError(_("Solo un supervisor puede rechazar novedades."))
        self.write({"state": "rejected", "approved_by": False, "approved_at": False})

    def action_reset(self):
        self.write({"state": "draft", "approved_by": False, "approved_at": False})

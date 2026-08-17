from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class CoPayrollNovelty(models.Model):
    _name = "l10n.co.payroll.novelty"
    _description = "Novedad laboral de nómina"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_from, employee_id"
    _check_company_auto = True

    name = fields.Char(string="Referencia", required=True, copy=False, default=lambda self: _("Novedad"), tracking=True)
    company_id = fields.Many2one(related="period_id.company_id", store=True, readonly=True)
    period_id = fields.Many2one("l10n.co.payroll.period", string="Periodo", required=True, ondelete="cascade", index=True, tracking=True)
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
    incapacity_origin = fields.Selection([
        ("common", "Enfermedad general"), ("work", "Origen laboral"),
        ("maternity", "Licencia de maternidad"), ("paternity", "Licencia de paternidad"),
    ], string="Origen / licencia", default="common", required=True)
    base_salary = fields.Monetary(string="Base diaria / salarial", currency_field="currency_id", help="Salario mensual usado para calcular el valor de la incapacidad. Si se diligencia, se divide entre 30.")
    amount_calculated = fields.Monetary(string="Valor calculado", compute="_compute_incapacity_amount", currency_field="currency_id")
    responsible_entity = fields.Selection([
        ("employer", "Empleador"), ("eps", "EPS"), ("arl", "ARL"), ("afp", "AFP"),
    ], string="Responsable", compute="_compute_responsible_entity", store=True)
    medical_certificate = fields.Char(string="Número de certificado / soporte")
    support_attachment_id = fields.Many2one("ir.attachment", string="Soporte", copy=False)
    affects_ibc = fields.Boolean(string="Afecta IBC", default=True)
    state = fields.Selection([
        ("draft", "Pendiente"), ("approved", "Aprobada"), ("applied", "Aplicada"), ("rejected", "Rechazada")
    ], string="Estado", default="draft", required=True, tracking=True)
    approved_by = fields.Many2one("res.users", string="Aprobada por", readonly=True, copy=False)
    approved_at = fields.Datetime(string="Fecha de aprobación", readonly=True, copy=False)
    notes = fields.Text(string="Observaciones")
    currency_id = fields.Many2one(related="period_id.currency_id", readonly=True)

    @api.depends("novelty_type", "incapacity_origin", "days")
    def _compute_responsible_entity(self):
        for novelty in self:
            origin = novelty.incapacity_origin
            novelty.responsible_entity = {
                "work": "arl", "maternity": "eps", "paternity": "eps",
            }.get(origin, "employer" if novelty.days <= 2 else "eps")

    @api.depends("days", "base_salary", "incapacity_origin", "period_id.parameter_id.minimum_wage")
    def _compute_incapacity_amount(self):
        for novelty in self:
            if novelty.novelty_type not in ("ige", "irl", "lma") or not novelty.days or not novelty.base_salary:
                novelty.amount_calculated = 0.0
                continue
            daily = novelty.base_salary / 30.0
            minimum_daily = (novelty.period_id.parameter_id.minimum_wage / 30.0) if novelty.period_id.parameter_id else 0.0
            remaining = novelty.days
            total = 0.0
            day = 1
            while remaining > 0:
                if novelty.incapacity_origin in ("work", "maternity", "paternity"):
                    rate = 1.0
                elif day <= 2:
                    rate = 1.0
                elif day <= 90:
                    rate = 2.0 / 3.0
                else:
                    rate = 0.5
                daily_value = daily * rate
                if novelty.incapacity_origin == "common" and minimum_daily:
                    daily_value = max(daily_value, minimum_daily)
                total += daily_value
                day += 1
                remaining -= 1
            novelty.amount_calculated = total

    def action_calculate_amount(self):
        for novelty in self:
            if novelty.amount_calculated <= 0:
                raise UserError(_("Diligencia días y base salarial para calcular la incapacidad."))
            novelty.write({"amount": novelty.amount_calculated})
        return True

    @api.constrains("date_from", "date_to", "days")
    def _check_dates_and_days(self):
        for novelty in self:
            if novelty.period_id and novelty.period_id.state in ("closed", "cancelled"):
                raise ValidationError(_("No puedes registrar o modificar novedades de un periodo cerrado o cancelado."))
            if novelty.date_from and novelty.date_to and novelty.date_from > novelty.date_to:
                raise ValidationError(_("La fecha inicial de la novedad no puede ser posterior a la fecha final."))
            if novelty.days < 0:
                raise ValidationError(_("Los días de una novedad no pueden ser negativos."))
            if novelty.novelty_type in ("ige", "irl", "lma") and novelty.days and not novelty.base_salary:
                raise ValidationError(_("Las incapacidades y licencias deben tener una base salarial para calcularse."))
            if novelty.period_id and novelty.date_from and novelty.date_to:
                if novelty.date_from < novelty.period_id.date_from or novelty.date_to > novelty.period_id.date_to:
                    raise ValidationError(_("La novedad debe estar dentro del periodo seleccionado."))

    def action_approve(self):
        if not (self.env.su or self.env.user._is_admin() or self.env.user.has_group("l10n_co_payroll.group_co_payroll_manager")):
            raise UserError(_("Solo un supervisor puede aprobar novedades."))
        if any(novelty.period_id.state in ("closed", "cancelled") for novelty in self):
            raise UserError(_("No puedes aprobar novedades de un periodo cerrado o cancelado."))
        self.write({"state": "approved", "approved_by": self.env.user.id, "approved_at": fields.Datetime.now()})

    def action_reject(self):
        if not (self.env.su or self.env.user._is_admin() or self.env.user.has_group("l10n_co_payroll.group_co_payroll_manager")):
            raise UserError(_("Solo un supervisor puede rechazar novedades."))
        self.write({"state": "rejected", "approved_by": False, "approved_at": False})

    def action_reset(self):
        self.write({"state": "draft", "approved_by": False, "approved_at": False})

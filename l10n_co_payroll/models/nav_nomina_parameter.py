from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class NavNominaParameter(models.Model):
    _name = "nav.nomina.parameter"
    _description = "Parámetros anuales de nómina colombiana"
    _order = "year desc, effective_from desc, version desc, company_id"
    _check_company_auto = True

    name = fields.Char(string="Nombre", compute="_compute_name", store=True)
    year = fields.Integer(string="Año", required=True, default=lambda self: fields.Date.context_today(self).year)
    version = fields.Integer(string="Versión", required=True, default=1, help="Permite conservar varias versiones legales durante un mismo año.")
    company_id = fields.Many2one("res.company", string="Compañía", required=True, default=lambda self: self.env.company)
    effective_from = fields.Date(string="Vigente desde", required=True, default=lambda self: fields.Date.context_today(self).replace(month=1, day=1), index=True)
    effective_to = fields.Date(string="Vigente hasta", required=True, default=lambda self: fields.Date.context_today(self).replace(month=12, day=31), index=True)
    status = fields.Selection([("draft", "Borrador"), ("active", "Activa"), ("archived", "Archivada")], string="Estado", required=True, default="active", index=True)
    legal_basis = fields.Text(string="Base legal", help="Norma, circular, resolución o fuente usada para esta versión.")
    reviewed_by = fields.Many2one("res.users", string="Revisada por", readonly=True, copy=False)
    reviewed_at = fields.Datetime(string="Fecha de revisión", readonly=True, copy=False)
    minimum_wage = fields.Monetary(string="Salario mínimo", currency_field="currency_id")
    transport_allowance = fields.Monetary(string="Auxilio de transporte", currency_field="currency_id")
    uvt_value = fields.Monetary(string="Valor UVT", currency_field="currency_id")
    health_employee_rate = fields.Float(string="Salud empleado (%)")
    pension_employee_rate = fields.Float(string="Pensión empleado (%)")
    solidarity_threshold_mw = fields.Float(string="Umbral solidaridad (SMLMV)")
    approval_mode = fields.Selection(
        [("none", "Sin aprobación adicional"), ("single", "Una aprobación"), ("double", "Doble aprobación")],
        string="Aprobación de cierre", default="none", required=True,
        help="Define si el cierre requiere aprobación de supervisor y si se necesitan dos usuarios distintos.",
    )
    block_on_warnings = fields.Boolean(
        string="Bloquear advertencias", default=False,
        help="Si está activo, las advertencias también impiden cerrar el periodo.",
    )
    require_novelty_approval = fields.Boolean(
        string="Exigir aprobación de novedades", default=True,
        help="Las novedades pendientes no permitirán cerrar cuando esté activo.",
    )
    weekly_hours = fields.Float(string="Jornada semanal de referencia", default=42.0)
    overtime_day_rate = fields.Float(string="Recargo hora extra diurna (%)")
    overtime_night_rate = fields.Float(string="Recargo hora extra nocturna (%)")
    night_rate = fields.Float(string="Recargo nocturno (%)")
    holiday_rate = fields.Float(string="Recargo dominical/festivo (%)")
    severance_rate = fields.Float(string="Provisión cesantías (%)")
    severance_interest_rate = fields.Float(string="Intereses cesantías (%)")
    vacation_rate = fields.Float(string="Provisión vacaciones (%)")
    bonus_rate = fields.Float(string="Provisión prima (%)")
    account_journal_id = fields.Many2one("account.journal", string="Diario de nómina", domain="[('company_id', '=', company_id), ('type', '=', 'general')]")
    expense_account_id = fields.Many2one("account.account", string="Cuenta gasto nómina", domain="[('company_ids', 'in', [company_id])]" )
    payroll_payable_account_id = fields.Many2one("account.account", string="Cuenta por pagar nómina", domain="[('company_ids', 'in', [company_id])]" )
    deductions_account_id = fields.Many2one("account.account", string="Cuenta deducciones / terceros", domain="[('company_ids', 'in', [company_id])]" )
    employer_account_id = fields.Many2one("account.account", string="Cuenta aportes empresa", domain="[('company_ids', 'in', [company_id])]" )
    analytic_account_id = fields.Many2one("account.analytic.account", string="Cuenta analítica", domain="[('company_id', '=', company_id)]")
    source_reference = fields.Char(string="Fuente / norma de referencia")
    withholding_notes = fields.Text(string="Notas tributarias")
    active = fields.Boolean(default=True)
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)
    rule_mapping_ids = fields.One2many("nav.nomina.rule.mapping", "parameter_id", string="Mapeo de conceptos")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            year = vals.get("year") or fields.Date.context_today(self).year
            vals.setdefault("effective_from", date(year, 1, 1))
            vals.setdefault("effective_to", date(year, 12, 31))
        return super().create(vals_list)

    @api.depends("year", "company_id")
    def _compute_name(self):
        for record in self:
            record.name = _("Parámetros %s v%s - %s") % (record.year, record.version, record.company_id.name)

    _company_year_unique = models.Constraint(
        "unique(company_id, year, version)",
        "Ya existe una configuración con esta versión para el año y compañía.",
    )

    @api.constrains("year", "version", "effective_from", "effective_to")
    def _check_year(self):
        for record in self:
            if record.year < 2000 or record.year > 2200:
                raise ValidationError(_("El año debe estar entre 2000 y 2200."))
            if record.version < 1:
                raise ValidationError(_("La versión debe ser mayor o igual a 1."))
            if record.effective_from > record.effective_to:
                raise ValidationError(_("La fecha inicial de vigencia no puede superar la fecha final."))
            if record.effective_from.year != record.year or record.effective_to.year != record.year:
                raise ValidationError(_("La vigencia debe estar dentro del año configurado."))
            overlap = self.search([
                ("id", "!=", record.id),
                ("company_id", "=", record.company_id.id),
                ("status", "!=", "archived"),
                ("effective_from", "<=", record.effective_to),
                ("effective_to", ">=", record.effective_from),
            ], limit=1)
            if overlap:
                raise ValidationError(_("La vigencia se cruza con %s. Ajusta las fechas o archiva la versión anterior.") % overlap.display_name)

    def action_activate(self):
        for record in self:
            record.write({"status": "active", "reviewed_by": self.env.user.id, "reviewed_at": fields.Datetime.now()})
        return True

    def action_archive(self):
        self.write({"status": "archived"})
        return True

import base64
import csv
import io
from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class CoPayrollParameter(models.Model):
    _name = "l10n.co.payroll.parameter"
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
    health_employee_rate = fields.Float(string="Salud empleado (%)", default=4.0)
    health_employer_rate = fields.Float(string="Salud empleador (%)", default=8.5)
    pension_employee_rate = fields.Float(string="Pensión empleado (%)", default=4.0)
    pension_employer_rate = fields.Float(string="Pensión empleador (%)", default=12.0)
    solidarity_threshold_mw = fields.Float(string="Umbral solidaridad (SMLMV)", default=4.0)
    solidarity_rate_1 = fields.Float(string="Fondo solidaridad 4–16 SMLMV (%)", default=1.0)
    solidarity_rate_2 = fields.Float(string="Fondo solidaridad 16–17 SMLMV (%)", default=1.2)
    solidarity_rate_3 = fields.Float(string="Fondo solidaridad 17–18 SMLMV (%)", default=1.4)
    solidarity_rate_4 = fields.Float(string="Fondo solidaridad 18–19 SMLMV (%)", default=1.6)
    solidarity_rate_5 = fields.Float(string="Fondo solidaridad 19–20 SMLMV (%)", default=1.8)
    solidarity_rate_6 = fields.Float(string="Fondo solidaridad más de 20 SMLMV (%)", default=2.0)
    arl_rate = fields.Float(string="ARL empleador (%)", default=0.522)
    ccf_rate = fields.Float(string="Caja de compensación (%)", default=4.0)
    sena_rate = fields.Float(string="SENA (%)", default=2.0)
    icbf_rate = fields.Float(string="ICBF (%)", default=3.0)
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
    overtime_day_rate = fields.Float(string="Recargo hora extra diurna (%)", default=25.0)
    overtime_night_rate = fields.Float(string="Recargo hora extra nocturna (%)", default=75.0)
    night_rate = fields.Float(string="Recargo nocturno (%)", default=35.0)
    holiday_rate = fields.Float(string="Recargo dominical/festivo vigente (%)", default=90.0)
    night_start_hour = fields.Float(string="Inicio jornada nocturna", default=19.0)
    night_end_hour = fields.Float(string="Fin jornada nocturna", default=6.0)
    severance_rate = fields.Float(string="Provisión cesantías mensual (%)", default=8.333333)
    severance_interest_rate = fields.Float(string="Intereses cesantías anual (%)", default=12.0)
    vacation_rate = fields.Float(string="Provisión vacaciones mensual (%)", default=4.166667)
    bonus_rate = fields.Float(string="Provisión prima mensual (%)", default=8.333333)
    severance_days_per_year = fields.Float(string="Cesantías (días por año)", default=30.0)
    vacation_days_per_year = fields.Float(string="Vacaciones (días por año)", default=15.0)
    bonus_days_per_year = fields.Float(string="Prima (días por año)", default=30.0)
    account_journal_id = fields.Many2one("account.journal", string="Diario de nómina", domain="[('company_id', '=', company_id), ('type', '=', 'general')]")
    expense_account_id = fields.Many2one("account.account", string="Cuenta gasto nómina", domain="[('company_ids', 'in', [company_id])]" )
    payroll_payable_account_id = fields.Many2one("account.account", string="Cuenta por pagar nómina", domain="[('company_ids', 'in', [company_id])]" )
    deductions_account_id = fields.Many2one("account.account", string="Cuenta deducciones / terceros", domain="[('company_ids', 'in', [company_id])]" )
    employer_account_id = fields.Many2one("account.account", string="Cuenta aportes empresa", domain="[('company_ids', 'in', [company_id])]" )
    analytic_account_id = fields.Many2one("account.analytic.account", string="Cuenta analítica", domain="[('company_id', '=', company_id)]")
    deduction_limit_ratio = fields.Float(string="Límite descuentos (%)", default=50.0, help="Límite preventivo de deducciones sobre el devengado.")
    minimum_ibc = fields.Monetary(string="IBC mínimo", currency_field="currency_id")
    minimum_ibc_multiple = fields.Float(string="IBC mínimo (SMLMV)", default=1.0, help="Se aplica proporcionalmente a los días reportados cuando está activo el control legal.")
    maximum_ibc_multiple = fields.Float(string="IBC máximo (SMLMV)", default=25.0)
    integral_salary_min_multiple = fields.Float(string="Salario integral mínimo (SMLMV)", default=13.0)
    integral_ibc_ratio = fields.Float(string="IBC salario integral (%)", default=70.0)
    transport_allowance_max_wage_multiple = fields.Float(string="Tope auxilio (SMLMV)", default=2.0)
    legal_validation_required = fields.Boolean(string="Exigir controles legales", default=True)
    source_reference = fields.Char(string="Fuente / norma de referencia")
    withholding_notes = fields.Text(string="Notas tributarias")
    active = fields.Boolean(default=True)
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)
    rule_mapping_ids = fields.One2many("l10n.co.payroll.rule.mapping", "parameter_id", string="Mapeo de conceptos")
    salary_rule_ids = fields.One2many("l10n.co.payroll.salary.rule", "parameter_id", string="Reglas salariales")

    def get_solidarity_rate(self, ibc):
        """Return the progressive FSP rate for an IBC expressed in pesos."""
        self.ensure_one()
        if not self.minimum_wage or not ibc or ibc < self.minimum_wage * self.solidarity_threshold_mw:
            return 0.0
        multiple = ibc / self.minimum_wage
        if multiple <= 16:
            return self.solidarity_rate_1
        if multiple <= 17:
            return self.solidarity_rate_2
        if multiple <= 18:
            return self.solidarity_rate_3
        if multiple <= 19:
            return self.solidarity_rate_4
        if multiple <= 20:
            return self.solidarity_rate_5
        return self.solidarity_rate_6

    def normalize_ibc(self, raw_ibc, worked_days=30.0, salary_mode="ordinary"):
        """Apply the configurable Colombian IBC floor, integral base and cap."""
        self.ensure_one()
        days = min(max(worked_days or 0.0, 0.0), 30.0)
        ibc = max(raw_ibc or 0.0, 0.0)
        if salary_mode == "integral":
            ibc *= self.integral_ibc_ratio / 100.0
        minimum = self.minimum_ibc or (self.minimum_wage * self.minimum_ibc_multiple if self.minimum_wage else 0.0)
        if minimum and days < 30:
            minimum *= days / 30.0
        maximum = self.minimum_wage * self.maximum_ibc_multiple if self.minimum_wage and self.maximum_ibc_multiple else 0.0
        if minimum:
            ibc = max(ibc, minimum)
        if maximum:
            ibc = min(ibc, maximum)
        return ibc

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

    @api.constrains(
        "health_employee_rate", "health_employer_rate", "pension_employee_rate", "pension_employer_rate",
        "solidarity_threshold_mw", "maximum_ibc_multiple", "integral_salary_min_multiple", "integral_ibc_ratio",
        "overtime_day_rate", "overtime_night_rate", "night_rate", "holiday_rate",
    )
    def _check_legal_values(self):
        for record in self:
            rates = (
                record.health_employee_rate, record.health_employer_rate, record.pension_employee_rate,
                record.pension_employer_rate, record.overtime_day_rate, record.overtime_night_rate,
                record.night_rate, record.holiday_rate, record.integral_ibc_ratio,
            )
            if any(rate < 0 or rate > 100 for rate in rates):
                raise ValidationError(_("Las tasas legales deben estar entre 0 y 100 por ciento."))
            if record.maximum_ibc_multiple and record.maximum_ibc_multiple < 1:
                raise ValidationError(_("El tope máximo de IBC debe ser al menos 1 SMLMV."))
            if record.integral_salary_min_multiple and record.integral_salary_min_multiple < 1:
                raise ValidationError(_("El mínimo de salario integral debe ser positivo."))
            if record.minimum_ibc_multiple < 0:
                raise ValidationError(_("El mínimo de IBC no puede ser negativo."))

    def action_activate(self):
        if not (self.env.su or self.env.user._is_admin() or self.env.user.has_group("l10n_co_payroll.group_co_payroll_manager")):
            raise ValidationError(_("Solo un supervisor puede activar una versión legal."))
        for record in self:
            invalid_rules = record.salary_rule_ids.filtered(lambda rule: rule.active and rule.validation_state != "valid")
            if invalid_rules:
                raise ValidationError(_("Valida todas las reglas salariales antes de activar la versión: %s.") % ", ".join(invalid_rules.mapped("code")))
            record.write({"status": "active", "reviewed_by": self.env.user.id, "reviewed_at": fields.Datetime.now()})
        return True

    def action_archive(self):
        if not (self.env.su or self.env.user._is_admin() or self.env.user.has_group("l10n_co_payroll.group_co_payroll_manager")):
            raise ValidationError(_("Solo un supervisor puede archivar una versión legal."))
        self.write({"status": "archived"})
        return True


class CoPayrollParameterImport(models.Model):
    _name = "l10n.co.payroll.parameter.import"
    _description = "Importación controlada de parámetros legales"
    _order = "create_date desc"
    _check_company_auto = True

    name = fields.Char(required=True, default=lambda self: _("Importación de parámetros legales"))
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    parameter_id = fields.Many2one("l10n.co.payroll.parameter", string="Versión destino", domain="[('company_id', '=', company_id), ('status', '=', 'draft')]")
    import_file = fields.Binary(string="CSV", required=True)
    filename = fields.Char()
    state = fields.Selection([("draft", "Pendiente"), ("imported", "Importado"), ("error", "Con errores")], default="draft", required=True)
    imported_count = fields.Integer(readonly=True)
    error_message = fields.Text(readonly=True)

    _ALLOWED_FIELDS = {
        "year": int, "version": int, "effective_from": str, "effective_to": str,
        "minimum_wage": float, "transport_allowance": float, "uvt_value": float,
        "health_employee_rate": float, "pension_employee_rate": float,
        "solidarity_threshold_mw": float, "weekly_hours": float,
        "overtime_day_rate": float, "overtime_night_rate": float, "night_rate": float,
        "holiday_rate": float, "severance_rate": float, "severance_interest_rate": float,
        "vacation_rate": float, "bonus_rate": float, "deduction_limit_ratio": float,
        "minimum_ibc": float, "minimum_ibc_multiple": float, "maximum_ibc_multiple": float,
        "integral_salary_min_multiple": float, "integral_ibc_ratio": float,
        "transport_allowance_max_wage_multiple": float,
        "health_employer_rate": float, "pension_employer_rate": float,
        "solidarity_rate_1": float, "solidarity_rate_2": float, "solidarity_rate_3": float,
        "solidarity_rate_4": float, "solidarity_rate_5": float, "solidarity_rate_6": float,
        "arl_rate": float, "ccf_rate": float, "sena_rate": float, "icbf_rate": float,
        "night_start_hour": float, "night_end_hour": float,
        "severance_days_per_year": float, "vacation_days_per_year": float, "bonus_days_per_year": float,
    }

    @staticmethod
    def _parse_number(value):
        text = str(value or "").strip().replace(" ", "")
        if "," in text and "." in text:
            text = text.replace(".", "").replace(",", ".") if text.rfind(",") > text.rfind(".") else text.replace(",", "")
        elif "," in text:
            text = text.replace(",", ".")
        elif text.count(".") > 1:
            text = text.replace(".", "")
        return text

    def action_import(self):
        for record in self:
            try:
                raw = base64.b64decode(record.import_file).decode("utf-8-sig", errors="replace")
                delimiter = ";" if raw.count(";") >= raw.count(",") else ","
                rows = list(csv.DictReader(io.StringIO(raw), delimiter=delimiter))
                if not rows:
                    raise ValidationError(_("El archivo no contiene filas."))
                row = {str(key).strip(): (value or "").strip() for key, value in rows[0].items() if key}
                vals = {}
                for field_name, converter in self._ALLOWED_FIELDS.items():
                    value = row.get(field_name)
                    if value in (None, ""):
                        continue
                    if converter is float:
                        vals[field_name] = converter(self._parse_number(value))
                    elif converter is int:
                        vals[field_name] = converter(float(self._parse_number(value)))
                    else:
                        vals[field_name] = value
                if "year" not in vals:
                    raise ValidationError(_("El CSV debe incluir el campo year."))
                if vals.get("effective_from"):
                    vals["effective_from"] = fields.Date.to_date(vals["effective_from"])
                if vals.get("effective_to"):
                    vals["effective_to"] = fields.Date.to_date(vals["effective_to"])
                target = record.parameter_id
                if target:
                    if target.status != "draft":
                        raise ValidationError(_("Solo puedes importar sobre una versión en borrador."))
                    target.write(vals)
                else:
                    vals["company_id"] = record.company_id.id
                    target = self.env["l10n.co.payroll.parameter"].create(vals)
                record.write({"parameter_id": target.id, "state": "imported", "imported_count": 1, "error_message": False})
            except Exception as error:
                record.write({"state": "error", "error_message": str(error), "imported_count": 0})
                raise
        return True

import base64
import csv
import io
from datetime import date

from dateutil.relativedelta import relativedelta

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
    arl_rate_class_1 = fields.Float(string="ARL clase I (%)", default=0.522)
    arl_rate_class_2 = fields.Float(string="ARL clase II (%)", default=1.044)
    arl_rate_class_3 = fields.Float(string="ARL clase III (%)", default=2.436)
    arl_rate_class_4 = fields.Float(string="ARL clase IV (%)", default=4.350)
    arl_rate_class_5 = fields.Float(string="ARL clase V (%)", default=6.960)
    ccf_rate = fields.Float(string="Caja de compensación (%)", default=4.0)
    sena_rate = fields.Float(string="SENA (%)", default=2.0)
    icbf_rate = fields.Float(string="ICBF (%)", default=3.0)
    employer_health_exempt = fields.Boolean(string="Exoneración salud empleador", default=False, help="Actívalo solo si la compañía cumple los requisitos legales de exoneración.")
    employer_sena_exempt = fields.Boolean(string="Exoneración SENA", default=False, help="Actívalo solo si la compañía cumple los requisitos legales aplicables.")
    employer_icbf_exempt = fields.Boolean(string="Exoneración ICBF", default=False, help="Actívalo solo si la compañía cumple los requisitos legales aplicables.")
    withholding_enabled = fields.Boolean(string="Aplicar retención en la fuente", default=False)
    withholding_procedure = fields.Selection([("1", "Procedimiento 1"), ("2", "Procedimiento 2")], string="Procedimiento de retención", default="1")
    pension_regime_mode = fields.Selection([
        ("legacy_law100", "Régimen vigente parametrizado"),
        ("reform_2381_pending", "Reforma pensional en revisión"),
    ], string="Marco pensional", default="legacy_law100", required=True,
        help="Permite mantener la operación parametrizada mientras se define la aplicación de cambios normativos.")
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
    overtime_daily_limit_hours = fields.Float(string="Límite diario horas extra", default=2.0, help="Control preventivo configurable; conserva la autorización y sus excepciones como soporte.")
    overtime_weekly_limit_hours = fields.Float(string="Límite semanal horas extra", default=12.0, help="Control preventivo configurable para la jornada ordinaria.")
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
    variable_average_months = fields.Integer(string="Meses para promedio variable", default=3, help="Meses históricos para promediar conceptos variables en liquidaciones.")
    variable_average_include_transport = fields.Boolean(string="Incluir auxilio en promedio", default=False)
    legal_validation_required = fields.Boolean(string="Exigir controles legales", default=True)
    social_profile_policy = fields.Selection([
        ("strict", "Exigir perfil PILA"),
        ("warn", "Advertir y permitir continuar"),
        ("optional", "No exigir perfil PILA"),
    ], string="Política de perfil PILA", default="warn", required=True, help="Controla qué ocurre si un empleado no tiene perfil PILA vigente.")
    source_reference = fields.Char(string="Fuente / norma de referencia")
    withholding_notes = fields.Text(string="Notas tributarias")
    active = fields.Boolean(default=True)
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)
    rule_mapping_ids = fields.One2many("l10n.co.payroll.rule.mapping", "parameter_id", string="Conceptos de nómina")
    salary_rule_ids = fields.One2many("l10n.co.payroll.salary.rule", "parameter_id", string="Reglas salariales")
    withholding_bracket_ids = fields.One2many("l10n.co.payroll.withholding.bracket", "parameter_id", string="Tabla de retención")

    def init(self):
        """Retire vistas nav_nomina obsoletas durante la actualización."""
        self.env.cr.execute(
            """
            UPDATE ir_ui_view AS view
               SET active = FALSE
             WHERE view.id IN (
                SELECT data.res_id
                  FROM ir_model_data AS data
                 WHERE data.model = 'ir.ui.view'
                   AND data.module = 'l10n_co_payroll'
                   AND data.name IN ('view_hr_payslip_nav_nomina', 'report_payslip_nav_nomina')
             )
            """
        )

        # Repair old databases where mappings were created before the
        # parametrizable salary rules and kept salary_rule_id empty.
        mappings = self.env["l10n.co.payroll.rule.mapping"].sudo().search([
            ("salary_rule_id", "=", False),
            ("parameter_id", "!=", False),
        ])
        for mapping in mappings:
            rule = self.env["l10n.co.payroll.salary.rule"].sudo().search([
                ("parameter_id", "=", mapping.parameter_id.id),
                ("company_id", "=", mapping.company_id.id),
                ("code", "=", mapping.code),
            ], limit=1)
            if rule:
                mapping.write({"salary_rule_id": rule.id, "is_system_default": True})

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

    def get_arl_rate(self, risk_class="I"):
        """Devuelve la tarifa inicial de ARL según la clase de riesgo."""
        self.ensure_one()
        return {
            "I": self.arl_rate_class_1 or self.arl_rate,
            "II": self.arl_rate_class_2,
            "III": self.arl_rate_class_3,
            "IV": self.arl_rate_class_4,
            "V": self.arl_rate_class_5,
        }.get(risk_class or "I", self.arl_rate)

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

    def calculate_withholding(self, taxable_income, exemptions=0.0):
        """Calcula una retención base con la tabla del artículo 383 del ET."""
        self.ensure_one()
        if not self.withholding_enabled or not self.uvt_value:
            return 0.0
        base = max((taxable_income or 0.0) - (exemptions or 0.0), 0.0)
        income_uvt = base / self.uvt_value
        brackets = self.env["l10n.co.payroll.withholding.bracket"].sudo().search([
            ("parameter_id", "=", self.id), ("active", "=", True),
        ], order="sequence, from_uvt")
        if not brackets:
            brackets = self.env["l10n.co.payroll.withholding.bracket"].default_brackets(self)
        bracket = brackets.filtered(lambda item: income_uvt > item.from_uvt and (not item.to_uvt or income_uvt <= item.to_uvt))[:1]
        if not bracket:
            return 0.0
        result_uvt = max(income_uvt - bracket.from_uvt, 0.0) * bracket.marginal_rate / 100.0 + bracket.fixed_uvt
        return round(max(result_uvt, 0.0) * self.uvt_value)

    def get_variable_average(self, employee, end_date, months=None):
        """Return the average variable payroll amount and the source count."""
        self.ensure_one()
        months = months or self.variable_average_months or 3
        end_date = fields.Date.to_date(end_date)
        start_date = end_date - relativedelta(months=months)
        slips = self.env["hr.payslip"].search([
            ("employee_id", "=", employee.id),
            ("company_id", "=", self.company_id.id),
            ("state", "in", ("validated", "paid", "done")),
            ("date_to", "<", end_date),
            ("date_from", ">=", start_date),
        ], order="date_to desc")
        values = []
        for slip in slips:
            gross = getattr(slip, "gross_wage", 0.0) or sum(line.total or 0.0 for line in slip.line_ids if getattr(line.category_id, "code", "") in ("GROSS", "BASIC"))
            basic = getattr(slip, "basic_wage", 0.0) or 0.0
            variable = max(gross - basic, 0.0)
            if self.variable_average_include_transport:
                variable += getattr(slip, "transport_allowance", 0.0) or 0.0
            values.append(variable)
        return (round(sum(values) / len(values), 2) if values else 0.0, len(values))

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
        "overtime_daily_limit_hours", "overtime_weekly_limit_hours",
        "arl_rate", "arl_rate_class_1", "arl_rate_class_2", "arl_rate_class_3", "arl_rate_class_4", "arl_rate_class_5",
    )
    def _check_legal_values(self):
        for record in self:
            rates = (
                record.health_employee_rate, record.health_employer_rate, record.pension_employee_rate,
                record.pension_employer_rate, record.overtime_day_rate, record.overtime_night_rate,
                record.night_rate, record.holiday_rate, record.integral_ibc_ratio,
                record.arl_rate, record.arl_rate_class_1, record.arl_rate_class_2,
                record.arl_rate_class_3, record.arl_rate_class_4, record.arl_rate_class_5,
            )
            if any(rate < 0 or rate > 100 for rate in rates):
                raise ValidationError(_("Las tasas legales deben estar entre 0 y 100 por ciento."))
            if record.maximum_ibc_multiple and record.maximum_ibc_multiple < 1:
                raise ValidationError(_("El tope máximo de IBC debe ser al menos 1 SMLMV."))
            if record.integral_salary_min_multiple and record.integral_salary_min_multiple < 1:
                raise ValidationError(_("El mínimo de salario integral debe ser positivo."))
            if record.minimum_ibc_multiple < 0:
                raise ValidationError(_("El mínimo de IBC no puede ser negativo."))
            if record.overtime_daily_limit_hours < 0 or record.overtime_weekly_limit_hours < 0:
                raise ValidationError(_("Los límites de horas extra no pueden ser negativos."))

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


class CoPayrollWithholdingBracket(models.Model):
    _name = "l10n.co.payroll.withholding.bracket"
    _description = "Rango de retención en la fuente"
    _order = "sequence, from_uvt"
    _check_company_auto = True

    name = fields.Char(string="Nombre", required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    parameter_id = fields.Many2one("l10n.co.payroll.parameter", required=True, ondelete="cascade", domain="[('company_id', '=', company_id)]")
    sequence = fields.Integer(default=10)
    from_uvt = fields.Float(string="Desde UVT", required=True)
    to_uvt = fields.Float(string="Hasta UVT")
    fixed_uvt = fields.Float(string="Impuesto fijo (UVT)", default=0.0)
    marginal_rate = fields.Float(string="Tarifa marginal (%)", default=0.0)
    active = fields.Boolean(default=True)
    legal_reference = fields.Char(string="Referencia legal", default="Artículo 383 del Estatuto Tributario")

    @api.constrains("parameter_id", "company_id", "from_uvt", "to_uvt", "fixed_uvt", "marginal_rate")
    def _check_values(self):
        for record in self:
            if record.parameter_id.company_id != record.company_id:
                raise ValidationError(_("El rango y sus parámetros deben pertenecer a la misma compañía."))
            if record.from_uvt < 0 or (record.to_uvt and record.to_uvt <= record.from_uvt):
                raise ValidationError(_("El rango de UVT no es válido."))
            if record.fixed_uvt < 0 or record.marginal_rate < 0 or record.marginal_rate > 100:
                raise ValidationError(_("Los valores de retención no son válidos."))

    @api.model
    def default_brackets(self, parameter):
        values = [
            (0, 95, 0, 0), (95, 150, 0, 19), (150, 360, 10, 28),
            (360, 640, 69, 33), (640, 945, 162, 35),
            (945, 2300, 268, 37), (2300, 0, 770, 39),
        ]
        model = self.sudo()
        records = model.browse()
        for index, (from_uvt, to_uvt, fixed_uvt, rate) in enumerate(values, 1):
            records |= model.create({
                "name": _("Rango %s") % index,
                "company_id": parameter.company_id.id,
                "parameter_id": parameter.id,
                "sequence": index * 10,
                "from_uvt": from_uvt,
                "to_uvt": to_uvt,
                "fixed_uvt": fixed_uvt,
                "marginal_rate": rate,
            })
        return records


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
        "variable_average_months": int, "variable_average_include_transport": bool,
        "health_employer_rate": float, "pension_employer_rate": float,
        "solidarity_rate_1": float, "solidarity_rate_2": float, "solidarity_rate_3": float,
        "solidarity_rate_4": float, "solidarity_rate_5": float, "solidarity_rate_6": float,
        "arl_rate": float, "ccf_rate": float, "sena_rate": float, "icbf_rate": float,
        "night_start_hour": float, "night_end_hour": float,
        "severance_days_per_year": float, "vacation_days_per_year": float, "bonus_days_per_year": float,
        "overtime_daily_limit_hours": float, "overtime_weekly_limit_hours": float,
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
                    elif converter is bool:
                        vals[field_name] = str(value).lower() in ("1", "true", "yes", "si", "sí")
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

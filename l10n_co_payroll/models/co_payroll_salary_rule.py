import ast
import math
import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError, UserError


_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{1,30}$")
_ALLOWED_NODES = (
    ast.Expression, ast.Constant, ast.Name, ast.Load, ast.BinOp, ast.UnaryOp,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.UAdd, ast.USub, ast.Not, ast.BoolOp, ast.And, ast.Or, ast.Compare,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.IfExp, ast.Call,
)
_ALLOWED_FUNCTIONS = {"abs", "min", "max", "round", "int", "float", "ceil", "floor"}


def _validate_formula(expression):
    """Validate the small, intentionally limited formula language."""
    if not expression or len(expression) > 500:
        raise ValidationError(_("La fórmula debe tener entre 1 y 500 caracteres."))
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as error:
        raise ValidationError(_("Fórmula inválida: %s") % error.msg) from error
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ValidationError(_("La fórmula contiene una operación no permitida: %s.") % type(node).__name__)
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            raise ValidationError(_("No se permiten nombres internos en las fórmulas."))
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_FUNCTIONS | {"rule", "source", "legal"}:
                raise ValidationError(_("Solo se permiten funciones matemáticas y rule(), source(), legal()."))
            if node.keywords:
                raise ValidationError(_("No se permiten argumentos nombrados en las fórmulas."))
    return tree


def _evaluate_formula(expression, values):
    tree = _validate_formula(expression)
    safe_globals = {"__builtins__": {}}
    safe_globals.update({name: getattr(math, name, None) for name in ("ceil", "floor")})
    safe_globals.update({"abs": abs, "min": min, "max": max, "round": round, "int": int, "float": float})
    safe_globals.update({name: values[name] for name in ("rule", "source", "legal")})
    safe_locals = {key: value for key, value in values.items() if not key.startswith("__")}
    try:
        result = eval(compile(tree, "<nomina_formula>", "eval"), safe_globals, safe_locals)
    except Exception as error:
        raise UserError(_("No se pudo evaluar la fórmula '%s': %s") % (expression, error)) from error
    if isinstance(result, bool):
        return result
    try:
        result = float(result or 0.0)
    except (TypeError, ValueError) as error:
        raise UserError(_("La fórmula '%s' debe devolver un número.") % expression) from error
    if not math.isfinite(result):
        raise UserError(_("La fórmula '%s' devolvió un valor no finito.") % expression)
    return result


def _evaluate_configured_rules(rules, values, salary_rule_totals, parameter):
    """Evaluate the configured Colombian rules over a normalized payslip base."""
    rules = rules.filtered("active").sorted(key=lambda rule: (rule.sequence, rule.id))
    calculated = {}
    legal_values = {field: getattr(parameter, field, 0.0) for field in (
        "minimum_wage", "transport_allowance", "uvt_value", "health_employee_rate",
        "health_employer_rate", "pension_employee_rate", "pension_employer_rate", "solidarity_threshold_mw", "weekly_hours",
        "overtime_day_rate", "overtime_night_rate", "night_rate", "holiday_rate",
        "night_start_hour", "night_end_hour", "severance_rate", "severance_interest_rate", "vacation_rate", "bonus_rate",
        "maximum_ibc_multiple", "integral_salary_min_multiple", "integral_ibc_ratio",
        "transport_allowance_max_wage_multiple", "overtime_daily_limit_hours", "overtime_weekly_limit_hours",
        "arl_rate", "arl_rate_class_1", "arl_rate_class_2", "arl_rate_class_3", "arl_rate_class_4", "arl_rate_class_5",
        "ccf_rate", "sena_rate", "icbf_rate", "employer_health_exempt", "employer_sena_exempt", "employer_icbf_exempt",
        "withholding_enabled", "withholding_procedure", "pension_regime_mode",
    )}
    legal_values["withholding_value"] = parameter.calculate_withholding(values.get("gross_wage", 0.0)) if parameter.withholding_enabled else 0.0
    if values.get("risk_class"):
        legal_values["arl_rate"] = parameter.get_arl_rate(values["risk_class"])

    def get_rule(code, default=0.0):
        return calculated.get(str(code).upper(), default)

    def get_source(code, default=0.0):
        return salary_rule_totals.get(str(code).upper(), default)

    def get_legal(code, default=0.0):
        return legal_values.get(str(code), default)

    context = dict(values)
    context.update({
        "minimum_wage": legal_values["minimum_wage"],
        "transport_allowance": legal_values["transport_allowance"],
        "uvt_value": legal_values["uvt_value"],
        "employee_count": values.get("employee_count", 1),
        "salary_mode": values.get("salary_mode", "ordinary"),
        "solidarity_rate": parameter.get_solidarity_rate(values.get("ibc_base") or values.get("basic_wage") or 0.0),
        "rule": get_rule,
        "source": get_source,
        "legal": get_legal,
    })
    results = []
    for rule in rules:
        context.update({
            "gross_wage": values["gross_wage"],
            "deduction_total": values["deduction_total"],
            "net_wage": values["net_wage"],
            "employer_cost": values["employer_cost"],
            "ibc_base": values["ibc_base"],
            "salary_mode": values.get("salary_mode", "ordinary"),
            "solidarity_rate": parameter.get_solidarity_rate(calculated.get("IBC_BASE", values["ibc_base"]) or 0.0),
        })
        condition_met = bool(_evaluate_formula(rule.condition, context))
        amount = float(_evaluate_formula(rule.amount_expression, context)) if condition_met else 0.0
        if rule.concept_type in ("ibc", "social_base"):
            amount = parameter.normalize_ibc(amount, values.get("worked_days", 30.0), values.get("salary_mode", "ordinary"))
        calculated[rule.code.upper()] = amount
        target = {"earning": "gross_wage", "deduction": "deduction_total", "employee_contribution": "deduction_total", "employer": "employer_cost", "employer_contribution": "employer_cost", "ibc": "ibc_base", "social_base": "ibc_base"}.get(rule.concept_type)
        if target:
            values[target] = amount if rule.impact == "replace" else values[target] + amount
            values["net_wage"] = values["gross_wage"] - values["deduction_total"]
        results.append({
            "rule_id": rule.id,
            "code": rule.code,
            "name": rule.name,
            "amount": amount,
            "condition_met": condition_met,
            "condition_snapshot": rule.condition,
            "formula_snapshot": rule.amount_expression,
        })
    values["rule_results"] = results
    return values


class CoPayrollSalaryRule(models.Model):
    _name = "l10n.co.payroll.salary.rule"
    _description = "Regla salarial parametrizable"
    _order = "sequence, code"
    _check_company_auto = True

    name = fields.Char(string="Nombre", required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    parameter_id = fields.Many2one("l10n.co.payroll.parameter", string="Versión legal", required=True, ondelete="cascade", domain="[('company_id', '=', company_id)]")
    sequence = fields.Integer(string="Secuencia", default=10)
    code = fields.Char(string="Código", required=True, help="Código único usado por otras fórmulas: rule('AUX_TRANSP').")
    concept_type = fields.Selection([
        ("earning", "Devengado"), ("deduction", "Deducción"), ("employee_contribution", "Aporte empleado"),
        ("employer", "Aporte empresa"), ("employer_contribution", "Aporte empleador"),
        ("ibc", "IBC"), ("social_base", "Base seguridad social"), ("provision", "Provisión"),
    ], string="Impacto", required=True, default="earning")
    impact = fields.Selection([("add", "Sumar al valor base"), ("replace", "Reemplazar valor base")], string="Operación", required=True, default="add")
    condition = fields.Char(string="Condición", required=True, default="True", help="Ejemplo: basic_wage <= minimum_wage * 2.")
    amount_expression = fields.Char(string="Fórmula", required=True, default="0.0", help="Ejemplo: min(transport_allowance, basic_wage * 0.10).")
    description = fields.Text(string="Descripción / soporte")
    is_system_default = fields.Boolean(string="Regla predeterminada del producto", default=False, readonly=True, copy=False)
    active = fields.Boolean(default=True)
    validation_state = fields.Selection([("pending", "Pendiente"), ("valid", "Válida"), ("error", "Con error")], default="pending", readonly=True, copy=False)
    validation_message = fields.Char(readonly=True, copy=False)
    validated_at = fields.Datetime(readonly=True, copy=False)
    native_rule_ids = fields.One2many("hr.salary.rule", "co_payroll_rule_id", string="Reglas nativas", readonly=True)
    test_ids = fields.One2many("l10n.co.payroll.salary.rule.test", "rule_id", string="Casos de prueba")

    _parameter_code_unique = models.Constraint("unique(parameter_id, code)", "Ya existe una regla con este código para la versión legal.")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals["code"] = (vals.get("code") or "").upper()
        return super().create(vals_list)

    def write(self, vals):
        vals = dict(vals)
        if "code" in vals:
            vals["code"] = (vals.get("code") or "").upper()
        if ({"code", "condition", "amount_expression"} & set(vals)) and "validation_state" not in vals:
            vals.update({"validation_state": "pending", "validation_message": False, "validated_at": False})
        return super().write(vals)

    @api.constrains("code", "condition", "amount_expression", "parameter_id", "company_id")
    def _check_rule(self):
        for record in self:
            code = (record.code or "").upper()
            if not _CODE_PATTERN.match(code):
                raise ValidationError(_("El código debe usar mayúsculas, números y guion bajo; debe empezar por una letra."))
            if record.parameter_id.company_id != record.company_id:
                raise ValidationError(_("La versión legal y la regla deben pertenecer a la misma compañía."))
            _validate_formula(record.condition)
            _validate_formula(record.amount_expression)

    def action_validate_formula(self):
        for record in self:
            try:
                _validate_formula(record.condition)
                _validate_formula(record.amount_expression)
            except ValidationError as error:
                record.write({"validation_state": "error", "validation_message": str(error), "validated_at": fields.Datetime.now()})
                raise
            record.write({"code": record.code.upper(), "validation_state": "valid", "validation_message": False, "validated_at": fields.Datetime.now()})
        return True

    def action_run_tests(self):
        self.mapped("test_ids").action_run()
        return True


class CoPayrollPeriodRuleResult(models.Model):
    _name = "l10n.co.payroll.period.rule.result"
    _description = "Resultado de regla salarial"
    _order = "sequence, id"
    _check_company_auto = True

    period_line_id = fields.Many2one("l10n.co.payroll.period.line", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="period_line_id.company_id", store=True, readonly=True)
    rule_id = fields.Many2one("l10n.co.payroll.salary.rule", string="Regla", required=True, ondelete="restrict")
    sequence = fields.Integer(related="rule_id.sequence", store=True, readonly=True)
    code = fields.Char(related="rule_id.code", store=True, readonly=True)
    name = fields.Char(related="rule_id.name", store=True, readonly=True)
    concept_type = fields.Selection(related="rule_id.concept_type", store=True, readonly=True)
    amount = fields.Monetary(string="Resultado", currency_field="currency_id", readonly=True)
    condition_met = fields.Boolean(string="Aplicada", readonly=True)
    condition_snapshot = fields.Char(string="Condición evaluada", readonly=True)
    formula_snapshot = fields.Char(string="Fórmula aplicada", readonly=True)
    currency_id = fields.Many2one(related="period_line_id.currency_id", readonly=True)


class CoPayrollSalaryRuleTest(models.Model):
    _name = "l10n.co.payroll.salary.rule.test"
    _description = "Caso de prueba de regla salarial"
    _order = "sequence, id"
    _check_company_auto = True

    name = fields.Char(required=True, default=lambda self: _("Caso de prueba"))
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    rule_id = fields.Many2one("l10n.co.payroll.salary.rule", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    basic_wage = fields.Float(string="Salario básico")
    gross_wage = fields.Float(string="Devengado")
    deduction_total = fields.Float(string="Deducciones")
    worked_days = fields.Float(string="Días trabajados", default=30.0)
    minimum_wage = fields.Float(string="Salario mínimo")
    transport_allowance = fields.Float(string="Auxilio transporte")
    expected_amount = fields.Float(string="Resultado esperado")
    tolerance = fields.Float(string="Tolerancia", default=0.01)
    actual_amount = fields.Float(string="Resultado obtenido", readonly=True)
    condition_met = fields.Boolean(string="Condición cumplida", readonly=True)
    state = fields.Selection([("draft", "Pendiente"), ("passed", "Correcto"), ("failed", "Falló")], default="draft", required=True, readonly=True)
    message = fields.Text(readonly=True)

    @api.constrains("rule_id", "company_id")
    def _check_company_rule(self):
        for record in self:
            if record.rule_id.company_id != record.company_id:
                raise ValidationError(_("El caso y la regla deben pertenecer a la misma compañía."))

    def action_run(self):
        for test in self:
            rule = test.rule_id
            values = {
                "basic_wage": test.basic_wage,
                "gross_wage": test.gross_wage,
                "deduction_total": test.deduction_total,
                "net_wage": test.gross_wage - test.deduction_total,
                "employer_cost": 0.0,
                "worked_days": test.worked_days,
                "worked_hours": 0.0,
                "ibc_base": test.basic_wage,
                "minimum_wage": test.minimum_wage,
                "transport_allowance": test.transport_allowance,
                "uvt_value": 0.0,
                "rule": lambda code, default=0.0: default,
                "source": lambda code, default=0.0: default,
                "legal": lambda code, default=0.0: default,
            }
            try:
                condition_met = bool(_evaluate_formula(rule.condition, values))
                actual = float(_evaluate_formula(rule.amount_expression, values)) if condition_met else 0.0
                passed = abs(actual - test.expected_amount) <= max(test.tolerance, 0.0)
                test.write({"actual_amount": actual, "condition_met": condition_met, "state": "passed" if passed else "failed", "message": _("Resultado coincide con el esperado.") if passed else _("Esperado: %s / obtenido: %s") % (test.expected_amount, actual)})
            except Exception as error:
                test.write({"state": "failed", "message": str(error), "condition_met": False})
        return True

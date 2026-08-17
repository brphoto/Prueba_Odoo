from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .co_payroll_salary_rule import _evaluate_configured_rules, _evaluate_formula


class HrSalaryRuleCoPayroll(models.Model):
    _inherit = "hr.salary.rule"

    co_payroll_rule_id = fields.Many2one("l10n.co.payroll.salary.rule", string="Regla Nómina Colombia", index=True, ondelete="set null")

    def _compute_rule(self, localdict):
        if self.co_payroll_rule_id:
            return self.co_payroll_rule_id._compute_native_rule(localdict)
        return super()._compute_rule(localdict)


class CoPayrollSalaryRuleNative(models.Model):
    _inherit = "l10n.co.payroll.salary.rule"

    def _ensure_native_rules(self, structures):
        NativeRule = self.env["hr.salary.rule"].sudo()
        category_refs = {
            "earning": "hr_payroll.ALW",
            "deduction": "hr_payroll.DED",
            "employee_contribution": "hr_payroll.DED",
            "employer": "hr_payroll.COMP",
            "employer_contribution": "hr_payroll.COMP",
            "ibc": "hr_payroll.BASIC",
            "social_base": "hr_payroll.BASIC",
            "provision": "hr_payroll.COMP",
        }
        for configured in self.filtered(lambda rule: rule.active and rule.concept_type in category_refs):
            for structure in structures:
                native = NativeRule.search([("co_payroll_rule_id", "=", configured.id), ("struct_id", "=", structure.id)], limit=1)
                if not native:
                    category = self.env.ref(category_refs[configured.concept_type], raise_if_not_found=False)
                    if not category:
                        continue
                    native = NativeRule.create({
                        "name": "[CO] %s" % configured.name,
                        "code": "CO_%s" % configured.code,
                        "struct_id": structure.id,
                        "sequence": 110 + min(max(configured.sequence, 1), 80),
                        "category_id": category.id,
                        "condition_select": "none",
                        "amount_select": "fix",
                        "amount_fix": 0.0,
                        "appears_on_payslip": configured.concept_type in ("earning", "deduction", "employee_contribution"),
                        "appears_on_employee_cost_dashboard": configured.concept_type in ("employer", "employer_contribution"),
                        "co_payroll_rule_id": configured.id,
                    })
        return True

    def _parameter_for_payslip(self, payslip):
        return self.env["l10n.co.payroll.parameter"].search([
            ("company_id", "=", payslip.company_id.id),
            ("effective_from", "<=", payslip.date_from),
            ("effective_to", ">=", payslip.date_to),
            ("status", "=", "active"),
            ("active", "=", True),
        ], order="version desc", limit=1)

    def _compute_native_rule(self, localdict):
        self.ensure_one()
        payslip = localdict.get("payslip")
        parameter = self._parameter_for_payslip(payslip) if payslip else self.env["l10n.co.payroll.parameter"]
        if not parameter or parameter != self.parameter_id or not self.active:
            return 0.0, 1.0, 100.0
        categories = localdict.get("categories", {})
        result_rules = localdict.get("result_rules", {})
        previous = localdict.setdefault("_co_formula_results", {})

        def get_rule(code, default=0.0):
            return previous.get(str(code).upper(), default)

        def get_source(code, default=0.0):
            code = str(code).upper()
            input_lines = self.env["hr.payslip.input"].search([
                ("payslip_id", "=", payslip.id if payslip else 0),
                ("input_type_id.code", "=", code),
            ]) if payslip else self.env["hr.payslip.input"]
            if input_lines:
                return sum(input_lines.mapped("amount"))
            source = (result_rules.get(code) or result_rules.get(str(code)) or {}).get("total")
            if source is not None:
                return source
            for input_line in (payslip.input_line_ids if payslip else self.env["hr.payslip.input"]):
                if input_line.input_type_id.code.upper() == code:
                    return input_line.amount or default
            return default

        legal = {field: getattr(parameter, field, 0.0) for field in (
            "minimum_wage", "transport_allowance", "uvt_value", "health_employee_rate", "health_employer_rate",
            "pension_employee_rate", "pension_employer_rate", "solidarity_threshold_mw", "weekly_hours",
            "overtime_day_rate", "overtime_night_rate", "night_rate", "holiday_rate",
            "transport_allowance_max_wage_multiple", "overtime_daily_limit_hours", "overtime_weekly_limit_hours",
            "ccf_rate", "sena_rate", "icbf_rate",
            "severance_rate", "severance_interest_rate", "vacation_rate", "bonus_rate", "arl_rate_class_1", "arl_rate_class_2",
            "arl_rate_class_3", "arl_rate_class_4", "arl_rate_class_5",
            "employer_health_exempt", "employer_sena_exempt", "employer_icbf_exempt",
            "withholding_enabled", "withholding_procedure", "pension_regime_mode",
        )}
        social = self.env["l10n.co.payroll.social"].get_for_employee(payslip.employee_id, payslip.date_from) if payslip else self.env["l10n.co.payroll.social"]
        if social:
            legal["arl_rate"] = parameter.get_arl_rate(social.risk_class)
        values = {
            "basic_wage": categories.get("BASIC", 0.0),
            "gross_wage": categories.get("GROSS", 0.0),
            "deduction_total": abs(categories.get("DED", 0.0)),
            "net_wage": categories.get("NET", 0.0),
            "employer_cost": categories.get("COMP", 0.0),
            "worked_days": sum(getattr(line, "number_of_days", 0.0) or 0.0 for line in (payslip.worked_days_line_ids if payslip else [])),
            "worked_hours": sum(getattr(line, "number_of_hours", 0.0) or 0.0 for line in (payslip.worked_days_line_ids if payslip else [])),
            "ibc_base": categories.get("BASIC", 0.0),
            "minimum_wage": legal["minimum_wage"],
            "transport_allowance": legal["transport_allowance"],
            "uvt_value": legal["uvt_value"],
            "employee_count": 1,
            "salary_mode": social.salary_mode if social else "ordinary",
            "solidarity_rate": parameter.get_solidarity_rate(categories.get("BASIC", 0.0)),
            "rule": get_rule,
            "source": get_source,
            "legal": lambda code, default=0.0: legal.get(str(code), default),
        }
        values["solidarity_rate"] = parameter.get_solidarity_rate(previous.get("IBC_BASE", values["ibc_base"]) or 0.0)
        legal["withholding_value"] = parameter.calculate_withholding(values.get("gross_wage", 0.0)) if parameter.withholding_enabled else 0.0
        condition = bool(_evaluate_formula(self.condition, values))
        amount = float(_evaluate_formula(self.amount_expression, values)) if condition else 0.0
        if self.concept_type in ("ibc", "social_base"):
            amount = parameter.normalize_ibc(amount, values.get("worked_days", 30.0), values.get("salary_mode", "ordinary"))
        previous[self.code.upper()] = amount
        if self.concept_type == "earning":
            delta = amount if self.impact == "add" else amount - values["gross_wage"]
        elif self.concept_type in ("deduction", "employee_contribution"):
            current = -values["deduction_total"]
            delta = -amount if self.impact == "add" else -amount - current
        elif self.concept_type in ("ibc", "social_base", "provision"):
            delta = 0.0
        else:
            delta = amount if self.impact == "add" else amount - values["employer_cost"]
        return delta, 1.0, 100.0


class HrPayslipCoPayroll(models.Model):
    _inherit = "hr.payslip"

    co_formula_applied = fields.Boolean(string="Reglas CO aplicadas", copy=False, readonly=True)
    co_formula_parameter_id = fields.Many2one("l10n.co.payroll.parameter", string="Versión legal aplicada", copy=False, readonly=True)
    co_formula_gross_wage = fields.Monetary(string="Devengado CO", currency_field="currency_id", copy=False, readonly=True)
    co_formula_deduction_total = fields.Monetary(string="Deducciones CO", currency_field="currency_id", copy=False, readonly=True)
    co_formula_net_wage = fields.Monetary(string="Neto CO", currency_field="currency_id", copy=False, readonly=True)
    co_formula_employer_cost = fields.Monetary(string="Costo empresa CO", currency_field="currency_id", copy=False, readonly=True)
    co_formula_ibc_base = fields.Monetary(string="IBC CO", currency_field="currency_id", copy=False, readonly=True)
    co_formula_breakdown = fields.Json(string="Detalle reglas CO", copy=False, readonly=True)
    co_formula_error = fields.Char(string="Error reglas CO", copy=False, readonly=True)

    def _co_parameters(self):
        Parameter = self.env["l10n.co.payroll.parameter"]
        result = {}
        for payslip in self:
            result[payslip.id] = Parameter.search([
                ("company_id", "=", payslip.company_id.id),
                ("effective_from", "<=", payslip.date_from),
                ("effective_to", ">=", payslip.date_to),
                ("status", "=", "active"),
                ("active", "=", True),
            ], order="version desc", limit=1)
        return result

    def _co_sync_rules(self):
        params = self._co_parameters()
        for payslip in self:
            parameter = params[payslip.id]
            if parameter and payslip.struct_id:
                parameter.salary_rule_ids._ensure_native_rules(payslip.struct_id)

    def compute_sheet(self):
        self._co_sync_rules()
        result = super().compute_sheet()
        self._co_finalize_rules()
        return result

    def action_co_recompute_rules(self):
        self.filtered(lambda slip: slip.state == "draft").compute_sheet()
        return True

    def _co_finalize_rules(self):
        for payslip in self.filtered(lambda slip: slip.state == "draft"):
            parameter = self._co_parameters().get(payslip.id)
            rules = parameter.salary_rule_ids if parameter else self.env["l10n.co.payroll.salary.rule"]
            if not parameter or not rules:
                payslip.write({"co_formula_applied": False, "co_formula_parameter_id": False, "co_formula_breakdown": False, "co_formula_error": False})
                continue
            try:
                native_lines = payslip.line_ids.filtered(lambda line: line.salary_rule_id.co_payroll_rule_id)
                base_lines = payslip.line_ids - native_lines
                base_by_code = defaultdict(float)
                base_categories = defaultdict(float)
                for line in base_lines:
                    base_by_code[line.code.upper()] += line.total or 0.0
                    base_categories[(line.category_id.code or "").upper()] += line.total or 0.0
                for input_line in payslip.input_line_ids:
                    input_code = input_line.input_type_id.code if input_line.input_type_id else False
                    if input_code:
                        base_by_code[input_code.upper()] += input_line.amount or 0.0
                social = self.env["l10n.co.payroll.social"].get_for_employee(payslip.employee_id, payslip.date_from)
                values = {
                    "basic_wage": base_by_code.get("BASIC", 0.0),
                    "gross_wage": base_by_code.get("GROSS", base_categories.get("GROSS", 0.0)),
                    "deduction_total": abs(base_categories.get("DED", 0.0)),
                    "net_wage": base_by_code.get("NET", 0.0),
                    "employer_cost": base_categories.get("COMP", 0.0),
                    "worked_days": sum(line.number_of_days or 0.0 for line in payslip.worked_days_line_ids),
                    "worked_hours": sum(line.number_of_hours or 0.0 for line in payslip.worked_days_line_ids),
                    "ibc_base": base_by_code.get("BASIC", 0.0),
                    "employee_count": 1,
                    "salary_mode": social.salary_mode if social else "ordinary",
                    "risk_class": social.risk_class if social else "I",
                }
                values["net_wage"] = values["gross_wage"] - values["deduction_total"]
                values = _evaluate_configured_rules(rules, values, base_by_code, parameter)
                payslip.write({
                    "co_formula_applied": True,
                    "co_formula_parameter_id": parameter.id,
                    "co_formula_gross_wage": values["gross_wage"],
                    "co_formula_deduction_total": values["deduction_total"],
                    "co_formula_net_wage": values["net_wage"],
                    "co_formula_employer_cost": values["employer_cost"],
                    "co_formula_ibc_base": values["ibc_base"],
                    "co_formula_breakdown": values.get("rule_results", []),
                    "co_formula_error": False,
                    "gross_wage": values["gross_wage"],
                    "net_wage": values["net_wage"],
                    "employer_cost": values["employer_cost"],
                })
            except Exception as error:
                payslip.write({"co_formula_applied": False, "co_formula_error": str(error)[:255]})
                raise

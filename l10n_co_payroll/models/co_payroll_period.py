import base64
import csv
import io
import time
from collections import defaultdict

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .co_payroll_salary_rule import _evaluate_formula


VALID_PAYSLIP_STATES = ("validated", "paid", "done")


class CoPayrollPeriod(models.Model):
    _name = "l10n.co.payroll.period"
    _description = "Periodo operativo de nómina"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_from desc, id desc"
    _check_company_auto = True

    name = fields.Char(string="Referencia", required=True, copy=False, default=lambda self: self.env["ir.sequence"].next_by_code("l10n.co.payroll.period") or _("Nuevo"), tracking=True)
    company_id = fields.Many2one("res.company", string="Compañía", required=True, default=lambda self: self.env.company, index=True, tracking=True)
    period_type = fields.Selection([("monthly", "Mensual"), ("biweekly", "Quincenal"), ("weekly", "Semanal"), ("off_cycle", "Extraordinario")], string="Tipo de nómina / frecuencia", required=True, default="monthly", tracking=True, help="Define la frecuencia del periodo. No crea una estructura salarial diferente.")
    date_from = fields.Date(string="Desde", required=True, default=lambda self: fields.Date.context_today(self).replace(day=1), tracking=True, index=True)
    date_to = fields.Date(string="Hasta", required=True, default=lambda self: fields.Date.context_today(self) + relativedelta(day=31), tracking=True, index=True)
    payment_date = fields.Date(string="Fecha de pago", tracking=True)
    employee_ids = fields.Many2many("hr.employee", "co_payroll_period_employee_rel", "period_id", "employee_id", string="Colaboradores a incluir", help="Déjalo vacío para incluir todos los colaboradores con recibos en el periodo.")
    department_ids = fields.Many2many("hr.department", "co_payroll_period_department_rel", "period_id", "department_id", string="Departamentos")
    job_ids = fields.Many2many("hr.job", "co_payroll_period_job_rel", "period_id", "job_id", string="Cargos")
    structure_ids = fields.Many2many("hr.payroll.structure", "co_payroll_period_structure_rel", "period_id", "structure_id", string="Estructuras salariales", domain=[("active", "=", True)])
    payslip_run_ids = fields.Many2many("hr.payslip.run", "co_payroll_period_run_rel", "period_id", "run_id", string="Lotes de nómina")
    parameter_id = fields.Many2one("l10n.co.payroll.parameter", string="Parámetros del año", domain="[('company_id', '=', company_id)]", help="Configuración anual de referencia. Los valores son editables y no calculan automáticamente el recibo.")
    approval_mode = fields.Selection([("none", "Sin aprobación adicional"), ("single", "Una aprobación"), ("double", "Doble aprobación")], string="Aprobación de cierre", default="none", required=True, tracking=True)
    approval_state = fields.Selection([("not_required", "No requerida"), ("pending", "Pendiente"), ("first_approved", "Primera aprobación"), ("approved", "Aprobada"), ("rejected", "Rechazada")], string="Estado aprobación", default="not_required", required=True, copy=False, tracking=True)
    block_on_warnings = fields.Boolean(string="Bloquear advertencias", default=False, tracking=True)
    require_novelty_approval = fields.Boolean(string="Exigir aprobación de novedades", default=True, tracking=True)
    approval_by = fields.Many2one("res.users", string="Primera aprobación", readonly=True, copy=False)
    approval_at = fields.Datetime(string="Fecha primera aprobación", readonly=True, copy=False)
    second_approval_by = fields.Many2one("res.users", string="Segunda aprobación", readonly=True, copy=False)
    second_approval_at = fields.Datetime(string="Fecha segunda aprobación", readonly=True, copy=False)
    rejection_reason = fields.Text(string="Motivo de rechazo", copy=False)
    source_payslip_ids = fields.Many2many("hr.payslip", string="Recibos encontrados", compute="_compute_source_payslip_ids")
    line_ids = fields.One2many("l10n.co.payroll.period.line", "period_id", string="Resumen por empleado", copy=False)
    issue_ids = fields.One2many("l10n.co.payroll.period.issue", "period_id", string="Detalle de validaciones", copy=False)
    diagnostic_ids = fields.One2many("l10n.co.payroll.period.diagnostic", "period_id", string="Diagnóstico integral", copy=False)
    novelty_ids = fields.One2many("l10n.co.payroll.novelty", "period_id", string="Detalle de novedades", copy=False)
    adjustment_ids = fields.One2many("l10n.co.payroll.adjustment", "period_id", string="Ajustes", copy=False)
    previous_period_id = fields.Many2one("l10n.co.payroll.period", string="Periodo anterior", compute="_compute_previous_period")
    state = fields.Selection([("draft", "Borrador"), ("ready", "Preparado"), ("closed", "Cerrado"), ("cancelled", "Cancelado")], string="Estado", default="draft", required=True, copy=False, tracking=True, index=True)
    is_sandbox = fields.Boolean(string="Modo sandbox", default=False, copy=False, index=True, help="Periodo de prueba aislado; no debe generar asientos ni pagos reales.")
    sandbox_source_id = fields.Many2one("l10n.co.payroll.period", string="Periodo origen", readonly=True, copy=False)
    sandbox_reason = fields.Char(string="Motivo sandbox", copy=False)
    rectifies_period_id = fields.Many2one("l10n.co.payroll.period", string="Rectifica periodo", readonly=True, copy=False, ondelete="restrict")
    rectification_ids = fields.One2many("l10n.co.payroll.period", "rectifies_period_id", string="Rectificaciones", readonly=True)
    is_rectification = fields.Boolean(string="Es rectificación", compute="_compute_is_rectification", store=True)
    rectification_reason = fields.Text(string="Motivo de rectificación", copy=False)
    cost_center_id = fields.Many2one("l10n.co.payroll.cost.center", string="Centro de costo general", domain="[('company_id', '=', company_id), ('active', '=', True)]")
    note = fields.Text(string="Notas")
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)
    payslip_count = fields.Integer(string="Recibos", compute="_compute_metrics")
    employee_count = fields.Integer(string="Empleados encontrados", compute="_compute_metrics")
    unvalidated_count = fields.Integer(string="Pendientes", compute="_compute_metrics")
    issue_count = fields.Integer(string="Hallazgos", compute="_compute_issue_metrics")
    blocking_issue_count = fields.Integer(string="Bloqueantes", compute="_compute_issue_metrics")
    warning_issue_count = fields.Integer(string="Advertencias", compute="_compute_issue_metrics")
    diagnostic_count = fields.Integer(string="Diagnósticos", compute="_compute_diagnostic_metrics")
    diagnostic_error_count = fields.Integer(string="Errores diagnóstico", compute="_compute_diagnostic_metrics")
    diagnostic_warning_count = fields.Integer(string="Advertencias diagnóstico", compute="_compute_diagnostic_metrics")
    novelty_count = fields.Integer(string="Novedades", compute="_compute_novelty_metrics")
    pending_novelty_count = fields.Integer(string="Novedades pendientes", compute="_compute_novelty_metrics")
    basic_total = fields.Monetary(string="Salario básico", compute="_compute_totals", currency_field="currency_id")
    gross_total = fields.Monetary(string="Total devengado", compute="_compute_totals", currency_field="currency_id")
    deduction_total = fields.Monetary(string="Deducciones", compute="_compute_totals", currency_field="currency_id")
    net_total = fields.Monetary(string="Neto a pagar", compute="_compute_totals", currency_field="currency_id")
    employer_total = fields.Monetary(string="Aportes empresa", compute="_compute_totals", currency_field="currency_id")
    adjustment_total = fields.Monetary(string="Ajustes aprobados", compute="_compute_totals", currency_field="currency_id")
    worked_days_total = fields.Float(string="Días trabajados", compute="_compute_totals")
    provision_severance = fields.Monetary(string="Provisión cesantías", compute="_compute_provisions", currency_field="currency_id")
    provision_severance_interest = fields.Monetary(string="Intereses cesantías", compute="_compute_provisions", currency_field="currency_id")
    provision_vacation = fields.Monetary(string="Provisión vacaciones", compute="_compute_provisions", currency_field="currency_id")
    provision_bonus = fields.Monetary(string="Provisión prima", compute="_compute_provisions", currency_field="currency_id")
    prepared_by = fields.Many2one("res.users", string="Preparado por", readonly=True, copy=False)
    prepared_at = fields.Datetime(string="Fecha de preparación", readonly=True, copy=False)
    closed_by = fields.Many2one("res.users", string="Cerrado por", readonly=True, copy=False)
    closed_at = fields.Datetime(string="Fecha de cierre", readonly=True, copy=False)
    last_check_at = fields.Datetime(string="Última validación", readonly=True, copy=False)
    processing_seconds = fields.Float(string="Tiempo de preparación (s)", readonly=True, copy=False)
    last_run_count = fields.Integer(string="Recibos procesados", readonly=True, copy=False)
    audit_event_ids = fields.One2many("l10n.co.payroll.audit", "period_id", string="Trazabilidad", readonly=True)

    @api.depends("rectifies_period_id")
    def _compute_is_rectification(self):
        for period in self:
            period.is_rectification = bool(period.rectifies_period_id)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            company_id = vals.get("company_id") or self.env.company.id
            date_from = fields.Date.to_date(vals.get("date_from")) or fields.Date.context_today(self)
            parameter = self.env["l10n.co.payroll.parameter"].search([
                ("company_id", "=", company_id),
                ("year", "=", date_from.year),
                ("status", "=", "active"),
                ("effective_from", "<=", date_from),
                ("effective_to", ">=", date_from),
                ("active", "=", True),
            ], order="version desc", limit=1)
            if parameter:
                vals.setdefault("parameter_id", parameter.id)
                vals.setdefault("approval_mode", parameter.approval_mode)
                vals.setdefault("block_on_warnings", parameter.block_on_warnings)
                vals.setdefault("require_novelty_approval", parameter.require_novelty_approval)
            vals.setdefault("approval_state", "not_required" if vals.get("approval_mode", "none") == "none" else "pending")
        return super().create(vals_list)

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for period in self:
            if period.date_from and period.date_to and period.date_from > period.date_to:
                raise ValidationError(_("La fecha inicial no puede ser posterior a la fecha final."))
            duplicate = self.search([("id", "!=", period.id), ("company_id", "=", period.company_id.id), ("date_from", "=", period.date_from), ("date_to", "=", period.date_to), ("state", "!=", "cancelled"), ("is_sandbox", "=", period.is_sandbox)], limit=1)
            if duplicate and duplicate.id != period.rectifies_period_id.id:
                raise ValidationError(_("Ya existe el periodo %s para estas fechas en la compañía.") % duplicate.display_name)

    @api.onchange("parameter_id")
    def _onchange_parameter(self):
        if self.parameter_id:
            self.approval_mode = self.parameter_id.approval_mode
            self.block_on_warnings = self.parameter_id.block_on_warnings
            self.require_novelty_approval = self.parameter_id.require_novelty_approval

    @api.onchange("date_from", "period_type")
    def _onchange_dates(self):
        if not self.date_from:
            return
        if self.period_type == "monthly":
            self.date_to = self.date_from + relativedelta(day=31)
        elif self.period_type == "biweekly":
            self.date_to = self.date_from.replace(day=15)
        elif self.period_type == "weekly":
            self.date_to = self.date_from + relativedelta(days=6)

    def _get_candidate_payslips(self):
        self.ensure_one()
        domain = [("company_id", "=", self.company_id.id), ("date_from", ">=", self.date_from), ("date_to", "<=", self.date_to), ("state", "!=", "cancel")]
        if self.employee_ids:
            domain.append(("employee_id", "in", self.employee_ids.ids))
        if self.department_ids:
            domain.append(("employee_id.department_id", "in", self.department_ids.ids))
        if self.job_ids:
            domain.append(("employee_id.job_id", "in", self.job_ids.ids))
        if self.structure_ids:
            domain.append(("struct_id", "in", self.structure_ids.ids))
        if self.payslip_run_ids:
            domain.append(("payslip_run_id", "in", self.payslip_run_ids.ids))
        return self.env["hr.payslip"].search(domain, order="employee_id, date_from, id")

    @api.depends("date_from", "date_to", "company_id", "employee_ids", "department_ids", "job_ids", "structure_ids", "payslip_run_ids")
    def _compute_source_payslip_ids(self):
        for period in self:
            period.source_payslip_ids = period._get_candidate_payslips() if period.date_from and period.date_to else False

    @api.depends("date_from", "date_to", "company_id", "employee_ids", "department_ids", "job_ids", "structure_ids", "payslip_run_ids", "line_ids")
    def _compute_metrics(self):
        for period in self:
            payslips = period._get_candidate_payslips()
            period.payslip_count = len(payslips)
            period.employee_count = len(period.line_ids) or len(payslips.mapped("employee_id"))
            period.unvalidated_count = len(payslips.filtered(lambda slip: slip.state not in VALID_PAYSLIP_STATES))

    @api.depends("issue_ids.severity")
    def _compute_issue_metrics(self):
        for period in self:
            period.issue_count = len(period.issue_ids)
            period.blocking_issue_count = len(period.issue_ids.filtered(lambda issue: issue.severity == "error"))
            period.warning_issue_count = len(period.issue_ids.filtered(lambda issue: issue.severity == "warning"))

    @api.depends("diagnostic_ids.severity", "diagnostic_ids.resolved")
    def _compute_diagnostic_metrics(self):
        for period in self:
            period.diagnostic_count = len(period.diagnostic_ids)
            period.diagnostic_error_count = len(period.diagnostic_ids.filtered(lambda item: item.severity == "error" and not item.resolved))
            period.diagnostic_warning_count = len(period.diagnostic_ids.filtered(lambda item: item.severity == "warning" and not item.resolved))

    @api.depends("novelty_ids.state")
    def _compute_novelty_metrics(self):
        for period in self:
            period.novelty_count = len(period.novelty_ids)
            period.pending_novelty_count = len(period.novelty_ids.filtered(lambda novelty: novelty.state == "draft"))

    @api.depends("date_from", "company_id")
    def _compute_previous_period(self):
        for period in self:
            period.previous_period_id = self.search([("id", "!=", period.id), ("company_id", "=", period.company_id.id), ("date_to", "<", period.date_from), ("state", "=", "closed")], order="date_to desc", limit=1) if period.date_from else False

    @api.depends("line_ids.basic_wage", "line_ids.gross_wage", "line_ids.deduction_total", "line_ids.net_wage", "line_ids.employer_cost", "line_ids.worked_days", "adjustment_ids.amount", "adjustment_ids.state")
    def _compute_totals(self):
        for period in self:
            period.basic_total = sum(period.line_ids.mapped("basic_wage"))
            period.gross_total = sum(period.line_ids.mapped("gross_wage"))
            period.deduction_total = sum(period.line_ids.mapped("deduction_total"))
            period.net_total = sum(period.line_ids.mapped("net_wage"))
            period.employer_total = sum(period.line_ids.mapped("employer_cost"))
            period.adjustment_total = sum(period.adjustment_ids.filtered(lambda adjustment: adjustment.state in ("approved", "applied")).mapped("amount"))
            period.worked_days_total = sum(period.line_ids.mapped("worked_days"))

    @api.depends("line_ids.provision_severance_base", "line_ids.provision_vacation_base", "line_ids.provision_bonus_base", "line_ids.worked_days", "parameter_id.severance_days_per_year", "parameter_id.severance_interest_rate", "parameter_id.vacation_days_per_year", "parameter_id.bonus_days_per_year")
    def _compute_provisions(self):
        for period in self:
            parameter = period.parameter_id
            if not parameter:
                period.provision_severance = period.provision_severance_interest = 0.0
                period.provision_vacation = period.provision_bonus = 0.0
                continue
            days = sum(period.line_ids.mapped("worked_days"))
            period.provision_severance = sum(period.line_ids.mapped("provision_severance_base")) * (parameter.severance_days_per_year / 30.0) * days / 360.0
            period.provision_severance_interest = period.provision_severance * parameter.severance_interest_rate / 100.0 * days / 360.0
            period.provision_vacation = sum(period.line_ids.mapped("provision_vacation_base")) * parameter.vacation_days_per_year / 360.0
            period.provision_bonus = sum(period.line_ids.mapped("provision_bonus_base")) * (parameter.bonus_days_per_year / 30.0) * days / 360.0

    @api.model
    def _summarize_payslips(self, payslips, parameter=None):
        if payslips and "co_formula_applied" in payslips._fields and all(payslips.mapped("co_formula_applied")):
            values = {
                "basic_wage": sum(payslips.mapped("basic_wage")),
                "gross_wage": sum(payslips.mapped("co_formula_gross_wage")),
                "deduction_total": sum(payslips.mapped("co_formula_deduction_total")),
                "net_wage": sum(payslips.mapped("co_formula_net_wage")),
                "employer_cost": sum(payslips.mapped("co_formula_employer_cost")),
                "worked_days": sum(sum(line.number_of_days or 0.0 for line in slip.worked_days_line_ids) for slip in payslips),
                "worked_hours": sum(sum(line.number_of_hours or 0.0 for line in slip.worked_days_line_ids) for slip in payslips),
                "overtime_day_hours": 0.0, "overtime_night_hours": 0.0, "night_hours": 0.0, "holiday_hours": 0.0,
                "ibc_base": sum(payslips.mapped("co_formula_ibc_base")),
                "rule_results": [],
            }
            result_by_rule = defaultdict(lambda: {"amount": 0.0, "condition_met": False, "condition_snapshot": False, "formula_snapshot": False})
            for slip in payslips:
                for input_line in slip.input_line_ids:
                    code = input_line.input_type_id.code.upper() if input_line.input_type_id else ""
                    field_name = {"HED": "overtime_day_hours", "HEN": "overtime_night_hours", "HDF": "holiday_hours", "RN": "night_hours"}.get(code)
                    if field_name:
                        values[field_name] += input_line.amount or 0.0
                for result in slip.co_formula_breakdown or []:
                    item = result_by_rule[result.get("rule_id")]
                    item["amount"] += result.get("amount", 0.0)
                    item["condition_met"] = item["condition_met"] or result.get("condition_met", False)
                    item["condition_snapshot"] = result.get("condition_snapshot")
                    item["formula_snapshot"] = result.get("formula_snapshot")
            values["rule_results"] = [{"rule_id": rule_id, **result} for rule_id, result in result_by_rule.items()]
            return self._add_legal_calculations(values, payslips, parameter)
        values = {"basic_wage": sum(payslips.mapped("basic_wage")), "gross_wage": sum(payslips.mapped("gross_wage")) if "gross_wage" in payslips._fields else 0.0, "deduction_total": 0.0, "net_wage": sum(payslips.mapped("net_wage")), "employer_cost": sum(payslips.mapped("employer_cost")) if "employer_cost" in payslips._fields else 0.0, "worked_days": 0.0, "worked_hours": 0.0, "overtime_day_hours": 0.0, "overtime_night_hours": 0.0, "night_hours": 0.0, "holiday_hours": 0.0, "ibc_base": 0.0}
        category_totals = defaultdict(float)
        mapped_totals = defaultdict(float)
        salary_rule_totals = defaultdict(float)
        mappings = {mapping.code: mapping for mapping in parameter.rule_mapping_ids.filtered("active")} if parameter else {}
        for slip in payslips:
            for line in slip.line_ids:
                category_totals[(getattr(line.category_id, "code", "") or "").upper()] += line.total or 0.0
                rule_code = getattr(getattr(line, "salary_rule_id", False), "code", False)
                if rule_code:
                    salary_rule_totals[rule_code.upper()] += line.total or 0.0
                mapping = mappings.get(rule_code)
                if mapping:
                    mapped_totals[mapping.concept_type] += line.total or 0.0
                    if mapping.include_in_ibc:
                        mapped_totals["ibc"] += line.total or 0.0
            for input_line in slip.input_line_ids:
                input_code = input_line.input_type_id.code if input_line.input_type_id else False
                if input_code:
                    salary_rule_totals[input_code.upper()] += input_line.amount or 0.0
                    hour_fields = {"HED": "overtime_day_hours", "HEN": "overtime_night_hours", "HDF": "holiday_hours", "RN": "night_hours"}
                    if input_code.upper() in hour_fields:
                        values[hour_fields[input_code.upper()]] += input_line.amount or 0.0
            for worked_day in slip.worked_days_line_ids:
                values["worked_days"] += worked_day.number_of_days or 0.0
                values["worked_hours"] += worked_day.number_of_hours or 0.0
        if not values["gross_wage"]:
            values["gross_wage"] = category_totals.get("GROSS") or category_totals.get("BASIC") or values["basic_wage"]
        values["gross_wage"] = mapped_totals.get("earning") or values["gross_wage"]
        values["deduction_total"] = abs(mapped_totals.get("deduction") or category_totals.get("DED", 0.0))
        if not values["employer_cost"]:
            values["employer_cost"] = mapped_totals.get("employer") or category_totals.get("COMP", 0.0)
        if not values["net_wage"]:
            values["net_wage"] = values["gross_wage"] - values["deduction_total"]
        values["ibc_base"] = mapped_totals.get("ibc") or category_totals.get("IBC") or values["basic_wage"]
        configured_rules = parameter.salary_rule_ids.filtered(lambda rule: rule.active and rule.company_id == parameter.company_id).sorted(key=lambda rule: (rule.sequence, rule.id)) if parameter and "salary_rule_ids" in parameter._fields else self.env["l10n.co.payroll.salary.rule"]
        if configured_rules:
            calculated = {}
            legal_values = {field: getattr(parameter, field, 0.0) for field in ("minimum_wage", "transport_allowance", "uvt_value", "health_employee_rate", "health_employer_rate", "pension_employee_rate", "pension_employer_rate", "solidarity_threshold_mw", "weekly_hours", "overtime_day_rate", "overtime_night_rate", "night_rate", "holiday_rate", "severance_rate", "severance_interest_rate", "vacation_rate", "bonus_rate", "maximum_ibc_multiple", "integral_ibc_ratio", "transport_allowance_max_wage_multiple", "overtime_daily_limit_hours", "overtime_weekly_limit_hours", "arl_rate", "ccf_rate", "sena_rate", "icbf_rate", "employer_health_exempt", "employer_sena_exempt", "employer_icbf_exempt", "withholding_enabled", "withholding_procedure", "pension_regime_mode")}
            legal_values["withholding_value"] = parameter.calculate_withholding(values.get("gross_wage", 0.0)) if parameter.withholding_enabled else 0.0
            def get_rule(code, default=0.0):
                return calculated.get(str(code).upper(), default)
            def get_source(code, default=0.0):
                return salary_rule_totals.get(str(code).upper(), default)
            def get_legal(code, default=0.0):
                return legal_values.get(str(code), default)
            context = dict(values)
            context.update({"minimum_wage": legal_values["minimum_wage"], "transport_allowance": legal_values["transport_allowance"], "uvt_value": legal_values["uvt_value"], "employee_count": len(payslips.mapped("employee_id")), "salary_mode": "ordinary", "solidarity_rate": parameter.get_solidarity_rate(values.get("ibc_base") or 0.0), "rule": get_rule, "source": get_source, "legal": get_legal})
            results = []
            for rule in configured_rules:
                context.update({"gross_wage": values["gross_wage"], "deduction_total": values["deduction_total"], "net_wage": values["net_wage"], "employer_cost": values["employer_cost"], "ibc_base": values["ibc_base"]})
                condition_met = bool(_evaluate_formula(rule.condition, context))
                amount = float(_evaluate_formula(rule.amount_expression, context)) if condition_met else 0.0
                calculated[rule.code.upper()] = amount
                target = {"earning": "gross_wage", "deduction": "deduction_total", "employee_contribution": "deduction_total", "employer": "employer_cost", "employer_contribution": "employer_cost", "ibc": "ibc_base", "social_base": "ibc_base"}.get(rule.concept_type)
                if target:
                    values[target] = amount if rule.impact == "replace" else values[target] + amount
                    values["net_wage"] = values["gross_wage"] - values["deduction_total"]
                results.append({"rule_id": rule.id, "amount": amount, "condition_met": condition_met, "condition_snapshot": rule.condition, "formula_snapshot": rule.amount_expression})
            values["net_wage"] = values["gross_wage"] - values["deduction_total"]
            values["rule_results"] = results
        return self._add_legal_calculations(values, payslips, parameter)

    @api.model
    def _add_legal_calculations(self, values, payslips, parameter):
        """Calcula bases y aportes auditables sin duplicarlos en el neto."""
        if not parameter or not payslips:
            return values
        worked_days = min(max(values.get("worked_days") or 0.0, 0.0), 30.0)
        social = self.env["l10n.co.payroll.social"].get_for_employee(payslips[0].employee_id, payslips[0].date_from)
        salary_mode = social.salary_mode if social else "ordinary"
        raw_ibc = values.get("ibc_base") or values.get("gross_wage") or values.get("basic_wage")
        values["ibc_base"] = parameter.normalize_ibc(raw_ibc, worked_days, salary_mode)
        values["social_ibc_base"] = values["ibc_base"]
        values["salary_mode"] = salary_mode
        values["transport_base"] = 0.0
        if parameter.transport_allowance and parameter.minimum_wage and values.get("basic_wage", 0.0) <= parameter.minimum_wage * parameter.transport_allowance_max_wage_multiple:
            values["transport_base"] = parameter.transport_allowance * worked_days / 30.0
        values["provision_severance_base"] = values.get("gross_wage", 0.0)
        values["provision_bonus_base"] = values.get("gross_wage", 0.0)
        values["provision_vacation_base"] = values.get("basic_wage", 0.0)
        values["health_employee"] = values["social_ibc_base"] * parameter.health_employee_rate / 100.0
        values["health_employer"] = 0.0 if parameter.employer_health_exempt else values["social_ibc_base"] * parameter.health_employer_rate / 100.0
        values["pension_employee"] = values["social_ibc_base"] * parameter.pension_employee_rate / 100.0
        values["pension_employer"] = values["social_ibc_base"] * parameter.pension_employer_rate / 100.0
        values["solidarity_rate"] = parameter.get_solidarity_rate(values["social_ibc_base"])
        values["solidarity_employee"] = values["social_ibc_base"] * values["solidarity_rate"] / 100.0
        risk_class = social.risk_class if social else "I"
        values["arl_employer"] = values["social_ibc_base"] * parameter.get_arl_rate(risk_class) / 100.0
        values["ccf_employer"] = values["social_ibc_base"] * parameter.ccf_rate / 100.0
        values["sena_employer"] = 0.0 if parameter.employer_sena_exempt else values["social_ibc_base"] * parameter.sena_rate / 100.0
        values["icbf_employer"] = 0.0 if parameter.employer_icbf_exempt else values["social_ibc_base"] * parameter.icbf_rate / 100.0
        values["social_employee_total"] = values["health_employee"] + values["pension_employee"] + values["solidarity_employee"]
        values["social_employer_total"] = values["health_employer"] + values["pension_employer"] + values["arl_employer"] + values["ccf_employer"] + values["sena_employer"] + values["icbf_employer"]
        return values

    def _run_validation(self, payslips=None):
        Issue = self.env["l10n.co.payroll.period.issue"]
        for period in self:
            current_payslips = payslips if payslips is not None else period._get_candidate_payslips()
            period.issue_ids.sudo().unlink()
            vals_list = []
            if not current_payslips:
                vals_list.append({"period_id": period.id, "severity": "error", "code": "NO_PAYSLIPS", "message": _("No se encontraron recibos en el rango seleccionado.")})
            for novelty in period.novelty_ids:
                if novelty.state == "draft":
                    vals_list.append({"period_id": period.id, "severity": "error" if period.require_novelty_approval else "warning", "code": "NOVELTY_PENDING", "message": _("La novedad %s de %s está pendiente de aprobación.") % (novelty.novelty_type.upper(), novelty.employee_id.name), "employee_id": novelty.employee_id.id})
                elif novelty.state == "rejected":
                    vals_list.append({"period_id": period.id, "severity": "warning", "code": "NOVELTY_REJECTED", "message": _("La novedad %s de %s fue rechazada.") % (novelty.novelty_type.upper(), novelty.employee_id.name), "employee_id": novelty.employee_id.id})
            for slip in current_payslips:
                employee = slip.employee_id
                social = self.env["l10n.co.payroll.social"].get_for_employee(employee, period.date_from)
                if not social:
                    policy = period.parameter_id.social_profile_policy if period.parameter_id else "warn"
                    if policy != "optional":
                        vals_list.append({"period_id": period.id, "severity": "error" if policy == "strict" else "warning", "code": "NO_SOCIAL_PROFILE", "message": _("%s no tiene un perfil PILA vigente para el periodo.") % employee.name, "employee_id": employee.id, "payslip_id": slip.id})
                elif social.coverage_mode == "full" and social.get_missing_administrators():
                    vals_list.append({"period_id": period.id, "severity": "error", "code": "MISSING_ADMINISTRATORS", "message": _("%s tiene administradoras PILA incompletas: %s.") % (employee.name, ", ".join(social.get_missing_administrators())), "employee_id": employee.id, "payslip_id": slip.id})
                elif social.coverage_mode in ("manual", "not_applicable") and not social.manual_reference:
                    vals_list.append({"period_id": period.id, "severity": "error", "code": "MISSING_COVERAGE_REFERENCE", "message": _("%s necesita una referencia para su modo PILA %s.") % (employee.name, social.coverage_mode), "employee_id": employee.id, "payslip_id": slip.id})
                if not employee.identification_id:
                    vals_list.append({"period_id": period.id, "severity": "warning", "code": "NO_IDENTIFICATION", "message": _("%s no tiene identificación configurada.") % employee.name, "employee_id": employee.id, "payslip_id": slip.id})
                if slip.state not in VALID_PAYSLIP_STATES:
                    vals_list.append({"period_id": period.id, "severity": "error", "code": "UNVALIDATED", "message": _("El recibo %s no está validado.") % slip.display_name, "employee_id": employee.id, "payslip_id": slip.id})
                if not getattr(slip, "version_id", False):
                    vals_list.append({"period_id": period.id, "severity": "error", "code": "NO_CONTRACT", "message": _("%s no tiene contrato/version vigente en el recibo.") % employee.name, "employee_id": employee.id, "payslip_id": slip.id})
                summary = self._summarize_payslips(slip, period.parameter_id)
                if summary["basic_wage"] <= 0:
                    vals_list.append({"period_id": period.id, "severity": "warning", "code": "ZERO_BASIC", "message": _("El salario básico de %s es cero o no está informado.") % employee.name, "employee_id": employee.id, "payslip_id": slip.id})
                if period.parameter_id and period.parameter_id.legal_validation_required:
                    if not period.parameter_id.minimum_wage:
                        vals_list.append({"period_id": period.id, "severity": "warning", "code": "MISSING_SMLMV", "message": _("La versión legal no tiene salario mínimo configurado."), "employee_id": employee.id, "payslip_id": slip.id})
                    if summary.get("salary_mode") == "integral" and summary["basic_wage"] < period.parameter_id.minimum_wage * period.parameter_id.integral_salary_min_multiple:
                        vals_list.append({"period_id": period.id, "severity": "error", "code": "INTEGRAL_BELOW_MINIMUM", "message": _("El salario integral de %s está por debajo del mínimo legal parametrizado de %s SMLMV.") % (employee.name, period.parameter_id.integral_salary_min_multiple), "employee_id": employee.id, "payslip_id": slip.id})
                    overtime_total = summary.get("overtime_day_hours", 0.0) + summary.get("overtime_night_hours", 0.0)
                    expected_daily_limit = period.parameter_id.overtime_daily_limit_hours * max(summary.get("worked_days", 0.0), 1.0)
                    expected_weekly_limit = period.parameter_id.overtime_weekly_limit_hours * max((summary.get("worked_days", 0.0) + 6.0) // 7.0, 1.0)
                    if overtime_total > expected_daily_limit or overtime_total > expected_weekly_limit:
                        vals_list.append({"period_id": period.id, "severity": "warning", "code": "OVERTIME_LIMIT", "message": _("Las horas extra de %s superan el control preventivo diario o semanal configurado; revisa autorización y soporte.") % employee.name, "employee_id": employee.id, "payslip_id": slip.id})
                    if period.parameter_id.minimum_wage and summary.get("social_ibc_base", 0.0) <= 0:
                        vals_list.append({"period_id": period.id, "severity": "error", "code": "ZERO_LEGAL_IBC", "message": _("El IBC legal de %s es cero.") % employee.name, "employee_id": employee.id, "payslip_id": slip.id})
                if summary["net_wage"] < 0:
                    vals_list.append({"period_id": period.id, "severity": "error", "code": "NEGATIVE_NET", "message": _("El neto de %s es negativo.") % employee.name, "employee_id": employee.id, "payslip_id": slip.id})
                if summary["gross_wage"] and summary["deduction_total"] > summary["gross_wage"]:
                    vals_list.append({"period_id": period.id, "severity": "error", "code": "DEDUCTIONS_GT_GROSS", "message": _("Las deducciones de %s superan el devengado.") % employee.name, "employee_id": employee.id, "payslip_id": slip.id})
            if vals_list:
                Issue.sudo().create(vals_list)
            period.last_check_at = fields.Datetime.now()
        return True

    def action_prepare(self):
        for period in self:
            started_at = time.monotonic()
            if period.state in ("closed", "cancelled"):
                raise UserError(_("Solo puedes preparar periodos en borrador o preparados."))
            payslips = period._get_candidate_payslips()
            if not payslips:
                period._run_validation(payslips)
                raise UserError(_("No se encontraron recibos de nómina en las fechas seleccionadas."))
            duplicate_lines = self.env["l10n.co.payroll.period.line"].search([
                ("period_id", "!=", period.id),
                ("period_id.state", "in", ("ready", "closed")),
                ("source_payslip_ids", "in", payslips.ids),
            ])
            if period.rectifies_period_id:
                duplicate_lines = duplicate_lines.filtered(lambda line: line.period_id != period.rectifies_period_id)
            if duplicate_lines:
                reused = duplicate_lines.mapped("source_payslip_ids")
                raise UserError(_(
                    "No se puede preparar porque %s recibo(s) ya pertenecen a un consolidado activo: %s. "
                    "Crea una rectificación del periodo original si corresponde."
                ) % (len(reused), ", ".join(reused.mapped("name")[:5])))
            period.line_ids.sudo().unlink()
            by_employee = defaultdict(lambda: self.env["hr.payslip"])
            for payslip in payslips:
                by_employee[payslip.employee_id.id] |= payslip
            previous_lines = {line.employee_id.id: line for line in period.previous_period_id.line_ids}
            line_model = self.env["l10n.co.payroll.period.line"].sudo()
            for employee_id, employee_payslips in by_employee.items():
                employee = employee_payslips[0].employee_id
                social = self.env["l10n.co.payroll.social"].get_for_employee(employee, period.date_from)
                summary = self._summarize_payslips(employee_payslips, period.parameter_id)
                rule_results = summary.pop("rule_results", [])
                previous = previous_lines.get(employee_id)
                previous_net = previous.net_wage if previous else 0.0
                variation = summary["net_wage"] - previous_net
                novelties = period.novelty_ids.filtered(lambda novelty: novelty.employee_id == employee and novelty.state in ("approved", "applied"))
                adjustments = period.adjustment_ids.filtered(lambda adjustment: adjustment.employee_id == employee and adjustment.state in ("approved", "applied"))
                line = line_model.create({"period_id": period.id, "employee_id": employee_id, "contract_id": employee_payslips[0].version_id.id if employee_payslips[0].version_id else False, "source_payslip_ids": [(6, 0, employee_payslips.ids)], "social_profile_id": social.id, "pila_type": social.contributor_type if social else "01", "pila_subtype": social.contributor_subtype if social else "0", "eps_code": social.eps_code if social else False, "pension_code": social.pension_code if social else False, "arl_code": social.arl_code if social else False, "ccf_code": social.ccf_code if social else False, "risk_class": social.risk_class if social else False, "novelty_count": len(novelties), "novelty_days": sum(novelties.mapped("days")), "pila_novelty_codes": ",".join(sorted(set(novelties.mapped("novelty_type")))) if novelties else False, "adjustment_total": sum(adjustments.mapped("amount")), "pila_status": "pending", "previous_net_wage": previous_net, "net_variation": variation, "comparison_state": "new" if not previous else ("changed" if abs(variation) > 0.01 else "unchanged"), **summary})
                cost_center = period.cost_center_id or self.env["l10n.co.payroll.cost.center"].get_for_employee(employee)
                if cost_center:
                    line.cost_center_id = cost_center.id
                line.write({
                    "pila_reporting_mode": social.coverage_mode if social else "missing",
                    "pila_manual_reference": social.manual_reference if social else False,
                })
                if social:
                    assignment_model = self.env["l10n.co.payroll.administrator.assignment"]
                    for administrator_field, code_field, kind in (("eps_id", "eps_code", "eps"), ("pension_id", "pension_code", "pension"), ("arl_id", "arl_code", "arl"), ("ccf_id", "ccf_code", "ccf")):
                        base_administrator = getattr(social, administrator_field, False)
                        assignment = assignment_model.get_for(period.company_id, employee, kind, base_administrator)
                        if assignment:
                            line[code_field] = assignment.administrator_id.code
                if rule_results:
                    self.env["l10n.co.payroll.period.rule.result"].sudo().create([dict(result, period_line_id=line.id) for result in rule_results])
                detail_values = self._get_consolidated_detail_values(employee_payslips, line)
                if detail_values:
                    self.env["l10n.co.payroll.period.detail"].sudo().create(detail_values)
            period._run_validation(payslips)
            period.action_run_diagnostics()
            period.novelty_ids.filtered(lambda novelty: novelty.state == "approved").write({"state": "applied"})
            period.write({"state": "ready", "approval_state": "not_required" if period.approval_mode == "none" else "pending", "approval_by": False, "approval_at": False, "second_approval_by": False, "second_approval_at": False, "rejection_reason": False, "prepared_by": self.env.user.id, "prepared_at": fields.Datetime.now(), "processing_seconds": time.monotonic() - started_at, "last_run_count": len(payslips)})
            self.env["l10n.co.payroll.audit"].sudo().create({"company_id": period.company_id.id, "res_model": period._name, "res_id": period.id, "action": "prepare", "description": _("Periodo preparado con %s recibos.") % len(payslips)})
        return self._reload_form()

    def action_run_checks(self):
        self._run_validation()
        self.action_run_diagnostics()
        self.env["l10n.co.payroll.audit"].sudo().create([{"company_id": period.company_id.id, "period_id": period.id, "res_model": period._name, "res_id": period.id, "action": "validate", "description": _("Validaciones ejecutadas.")} for period in self])
        return self._reload_form()

    def action_run_diagnostics(self):
        """Run one checklist across payroll, PILA, accounting and DIAN."""
        Diagnostic = self.env["l10n.co.payroll.period.diagnostic"].sudo()
        for period in self:
            Diagnostic.search([("period_id", "=", period.id)]).unlink()
            values = []

            def add(kind, severity, code, message, line=False, payslip=False):
                values.append({
                    "period_id": period.id,
                    "period_line_id": line.id if line else False,
                    "employee_id": line.employee_id.id if line else (payslip.employee_id.id if payslip else False),
                    "payslip_id": payslip.id if payslip else False,
                    "diagnostic_type": kind,
                    "severity": severity,
                    "code": code,
                    "message": message,
                })

            if not period.line_ids:
                add("payroll", "error", "NO_CONSOLIDATED_LINES", _("El periodo todavía no tiene consolidado por empleado."))

            for line in period.line_ids:
                employee = line.employee_id
                if not employee.identification_id:
                    add("payroll", "warning", "NO_IDENTIFICATION", _("%s no tiene identificación configurada.") % employee.name, line=line)
                if not line.source_payslip_ids:
                    add("payroll", "error", "NO_SOURCE_PAYSLIP", _("%s no tiene recibos fuente en el consolidado.") % employee.name, line=line)
                if line.net_wage < 0:
                    add("payroll", "error", "NEGATIVE_NET", _("El neto consolidado de %s es negativo.") % employee.name, line=line)
                if line.worked_days < 0 or line.worked_days > 31:
                    add("payroll", "error", "INVALID_WORKED_DAYS", _("Los días trabajados de %s están fuera del rango permitido.") % employee.name, line=line)
                parameter = period.parameter_id
                if parameter and parameter.deduction_limit_ratio and line.gross_wage and line.deduction_total / line.gross_wage * 100 > parameter.deduction_limit_ratio:
                    add("payroll", "warning", "DEDUCTION_LIMIT", _("Las deducciones de %s superan el %s%% parametrizado.") % (employee.name, parameter.deduction_limit_ratio), line=line)
                if not employee.bank_account_ids:
                    add("payment", "warning", "NO_BANK_ACCOUNT", _("%s no tiene cuenta bancaria para pago.") % employee.name, line=line)

                if line.pila_reporting_mode == "missing":
                    policy = period.parameter_id.social_profile_policy if period.parameter_id else "warn"
                    if policy != "optional":
                        add("pila", "error" if policy == "strict" else "warning", "NO_SOCIAL_PROFILE", _("%s no tiene perfil PILA vigente.") % employee.name, line=line)
                elif line.pila_reporting_mode == "full":
                    missing = line.social_profile_id.get_missing_administrators() if line.social_profile_id else [_("Perfil PILA")]
                    if missing:
                        add("pila", "error", "MISSING_ADMINISTRATORS", _("%s tiene administradoras PILA incompletas: %s.") % (employee.name, ", ".join(missing)), line=line)
                    if line.social_ibc_base <= 0 and line.worked_days > 0:
                        add("pila", "error", "ZERO_LEGAL_IBC", _("El IBC legal de %s es cero.") % employee.name, line=line)
                elif not line.pila_manual_reference:
                    add("pila", "error", "MISSING_COVERAGE_REFERENCE", _("%s requiere referencia para su modo PILA.") % employee.name, line=line)

                # The administrator catalog is also the accounting routing
                # table. Keep this as a warning because the summarized
                # fallback accounts still allow a period to be posted, but
                # make the missing third-party setup visible before posting.
                if line.social_profile_id and line.pila_reporting_mode == "full":
                    administrator_model = self.env["l10n.co.payroll.administrator.assignment"]
                    social = line.social_profile_id
                    for administrator, label in (
                        (social.eps_id, _("EPS")),
                        (social.pension_id, _("AFP")),
                        (social.arl_id, _("ARL")),
                        (social.ccf_id, _("Caja")),
                    ):
                        if not administrator:
                            continue
                        assignment = administrator_model.get_for(period.company_id, employee, administrator.kind, administrator)
                        resolved = assignment.administrator_id if assignment else administrator
                        debit_account = (assignment.debit_account_id if assignment and assignment.debit_account_id else resolved.debit_account_id)
                        credit_account = (assignment.credit_account_id if assignment and assignment.credit_account_id else resolved.credit_account_id)
                        partner = (assignment.partner_id if assignment and assignment.partner_id else resolved.partner_id)
                        if not debit_account and not credit_account:
                            add("accounting", "warning", "ADMINISTRATOR_ACCOUNTS", _("%s de %s no tiene cuenta débito ni crédito; se usará el resumen contable general.") % (label, employee.name), line=line)
                        if not partner:
                            add("accounting", "warning", "ADMINISTRATOR_PARTNER", _("%s de %s no tiene tercero contable configurado.") % (label, employee.name), line=line)

            if hasattr(period, "_get_accounting_accounts"):
                accounts = period._get_accounting_accounts()
                missing_accounts = [label for key, label in (("journal", "diario"), ("expense", "gasto"), ("payable", "por pagar"), ("deductions", "deducciones"), ("employer", "aportes empresa")) if not accounts.get(key)]
                if missing_accounts:
                    add("accounting", "warning", "ACCOUNTING_SETUP", _("Falta parametrizar contabilidad: %s.") % ", ".join(missing_accounts))

            if "l10n.co.payroll.dian.document" in self.env.registry.models and getattr(period.company_id, "co_dian_payroll_enabled", False):
                DianDocument = self.env["l10n.co.payroll.dian.document"]
                for line in period.line_ids.filtered(lambda item: item.pila_reporting_mode == "full"):
                    documents = DianDocument.search([("period_line_id", "=", line.id), ("is_adjustment", "=", False)])
                    if not documents:
                        add("dian", "warning", "DIAN_NOT_GENERATED", _("%s no tiene documento DIAN generado.") % line.employee_id.name, line=line)
                    else:
                        if len(documents) > 1:
                            add("dian", "error", "DIAN_MULTIPLE_DOCUMENTS", _("%s tiene %s documentos DIAN normales; el consolidado debe tener uno solo.") % (line.employee_id.name, len(documents)), line=line)
                        failed = documents.filtered(lambda doc: doc.state in ("error", "rejected"))[:1]
                        if failed:
                            add("dian", "error", "DIAN_ERROR", _("El documento DIAN de %s está en estado %s.") % (line.employee_id.name, failed.state), line=line)

            if values:
                Diagnostic.create(values)
            period.last_check_at = fields.Datetime.now()
        return self._reload_form()

    def action_open_diagnostics(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": _("Diagnóstico integral"), "res_model": "l10n.co.payroll.period.diagnostic", "view_mode": "list,form", "domain": [("period_id", "=", self.id)], "context": {"create": False, "delete": False}}

    def action_approve(self):
        if not (self.env.su or self.env.user._is_admin() or self.env.user.has_group("l10n_co_payroll.group_co_payroll_manager")):
            raise UserError(_("Solo un supervisor puede aprobar el cierre."))
        for period in self:
            if period.state != "ready":
                raise UserError(_("El periodo debe estar preparado antes de aprobarlo."))
            period._run_validation()
            if period.blocking_issue_count or (period.block_on_warnings and period.warning_issue_count):
                raise UserError(_("Corrige los hallazgos antes de aprobar el cierre."))
            if period.approval_mode == "none":
                raise UserError(_("Este periodo está configurado sin aprobación adicional."))
            if period.approval_state in ("pending", "rejected"):
                period.write({"approval_state": "approved" if period.approval_mode == "single" else "first_approved", "approval_by": self.env.user.id, "approval_at": fields.Datetime.now(), "rejection_reason": False})
            elif period.approval_mode == "double" and period.approval_state == "first_approved":
                if period.approval_by == self.env.user:
                    raise UserError(_("La segunda aprobación debe realizarla un usuario supervisor diferente."))
                period.write({"approval_state": "approved", "second_approval_by": self.env.user.id, "second_approval_at": fields.Datetime.now()})
            else:
                raise UserError(_("El periodo ya está aprobado."))
            self.env["l10n.co.payroll.audit"].sudo().create({"company_id": period.company_id.id, "period_id": period.id, "res_model": period._name, "res_id": period.id, "action": "approve", "description": _("Aprobación registrada en modo %s.") % period.approval_mode})
        return self._reload_form()

    def action_reject_approval(self):
        if not (self.env.su or self.env.user._is_admin() or self.env.user.has_group("l10n_co_payroll.group_co_payroll_manager")):
            raise UserError(_("Solo un supervisor puede rechazar el cierre."))
        self.write({"approval_state": "rejected", "rejection_reason": _("Rechazado por %s") % self.env.user.name, "second_approval_by": False, "second_approval_at": False})
        self.env["l10n.co.payroll.audit"].sudo().create([{"company_id": period.company_id.id, "period_id": period.id, "res_model": period._name, "res_id": period.id, "action": "reject", "description": period.rejection_reason or _("Aprobación rechazada.")} for period in self])
        return self._reload_form()

    def action_close(self):
        for period in self:
            if period.state != "ready":
                raise UserError(_("Primero prepara el resumen del periodo."))
            period._run_validation()
            if period.blocking_issue_count or (period.block_on_warnings and period.warning_issue_count):
                issues_to_show = period.issue_ids.filtered(lambda issue: issue.severity == "error") or period.issue_ids.filtered(lambda issue: issue.severity == "warning")
                messages = ", ".join(issues_to_show.mapped("message")[:3])
                raise UserError(_("No se puede cerrar: %s") % messages)
            if period.approval_mode != "none" and period.approval_state != "approved":
                raise UserError(_("El cierre requiere completar la aprobación configurada: %s.") % dict(period._fields["approval_state"].selection).get(period.approval_state))
            if not (self.env.su or self.env.user._is_admin() or self.env.user.has_group("l10n_co_payroll.group_co_payroll_manager")):
                raise UserError(_("Solo un supervisor puede cerrar un periodo."))
            period.write({"state": "closed", "closed_by": self.env.user.id, "closed_at": fields.Datetime.now()})
            self.env["l10n.co.payroll.audit"].sudo().create({"company_id": period.company_id.id, "period_id": period.id, "res_model": period._name, "res_id": period.id, "action": "close", "description": _("Periodo cerrado.")})
        return self._reload_form()

    def action_set_draft(self):
        for period in self:
            if period.state == "closed":
                raise UserError(_("Un periodo cerrado no se puede devolver a borrador."))
            period.write({"state": "draft", "approval_state": "not_required" if period.approval_mode == "none" else "pending", "approval_by": False, "approval_at": False, "second_approval_by": False, "second_approval_at": False})

    def action_cancel(self):
        if not (self.env.su or self.env.user._is_admin() or self.env.user.has_group("l10n_co_payroll.group_co_payroll_manager")):
            raise UserError(_("Solo un supervisor puede cancelar un periodo."))
        if any(period.state == "closed" for period in self):
            raise UserError(_("Un periodo cerrado no se puede cancelar."))
        self.write({"state": "cancelled"})
        self.env["l10n.co.payroll.audit"].sudo().create([{"company_id": period.company_id.id, "period_id": period.id, "res_model": period._name, "res_id": period.id, "action": "cancel", "description": _("Periodo cancelado.")} for period in self])

    def action_open_payslips(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": _("Recibos del periodo"), "res_model": "hr.payslip", "view_mode": "list,form", "domain": [("id", "in", self.source_payslip_ids.ids)], "context": {"create": False}}

    def action_open_lines(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": _("Consolidado por empleado"), "res_model": "l10n.co.payroll.period.line", "view_mode": "list,form", "domain": [("period_id", "=", self.id)], "context": {"create": False, "delete": False}}

    def action_open_issues(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": _("Hallazgos de validación"), "res_model": "l10n.co.payroll.period.issue", "view_mode": "list,form", "domain": [("period_id", "=", self.id)], "context": {"create": False, "delete": False}}

    def action_open_novelties(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": _("Novedades del periodo"), "res_model": "l10n.co.payroll.novelty", "view_mode": "list,form", "domain": [("period_id", "=", self.id)], "context": {"create": False}}

    def action_open_previous_period(self):
        self.ensure_one()
        if not self.previous_period_id:
            raise UserError(_("No hay un periodo anterior cerrado para comparar."))
        return {"type": "ir.actions.act_window", "name": _("Periodo anterior"), "res_model": self._name, "view_mode": "form", "res_id": self.previous_period_id.id}

    def action_create_rectification(self):
        self.ensure_one()
        if self.state != "closed":
            raise UserError(_("Solo puedes crear una rectificación desde un periodo cerrado."))
        existing = self.search([("rectifies_period_id", "=", self.id), ("state", "!=", "cancelled")], limit=1)
        if existing:
            return {"type": "ir.actions.act_window", "res_model": self._name, "view_mode": "form", "res_id": existing.id}
        rectification = self.create({
            "name": _("Rectificación de %s") % self.name,
            "company_id": self.company_id.id,
            "period_type": self.period_type,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "payment_date": self.payment_date,
            "parameter_id": self.parameter_id.id,
            "rectifies_period_id": self.id,
            "rectification_reason": _("Rectificación creada desde el periodo cerrado %s.") % self.name,
        })
        self.env["l10n.co.payroll.audit"].sudo().create({"company_id": self.company_id.id, "period_id": self.id, "res_model": rectification._name, "res_id": rectification.id, "action": "other", "description": _("Rectificación %s creada.") % rectification.name})
        return {"type": "ir.actions.act_window", "res_model": self._name, "view_mode": "form", "res_id": rectification.id}

    @api.model
    def _get_consolidated_detail_values(self, payslips, period_line):
        grouped = {}
        for slip in payslips:
            for result in slip.line_ids:
                rule = getattr(result, "salary_rule_id", False)
                code = (rule.code if rule else "") or getattr(result.category_id, "code", "") or "CONCEPTO"
                key = ("rule", code)
                item = grouped.setdefault(key, {"detail_type": "rule", "code": code, "name": rule.name if rule else result.name, "quantity": 0.0, "amount": 0.0, "source_payslip_ids": set()})
                item["quantity"] += getattr(result, "quantity", 0.0) or 0.0
                item["amount"] += result.total or 0.0
                item["source_payslip_ids"].add(slip.id)
            for worked in slip.worked_days_line_ids:
                work_type = getattr(worked, "work_entry_type_id", False)
                code = (work_type.code if work_type else "") or "JORNADA"
                key = ("worked_day", code)
                item = grouped.setdefault(key, {"detail_type": "worked_day", "code": code, "name": work_type.name if work_type else code, "quantity": 0.0, "amount": 0.0, "source_payslip_ids": set()})
                item["quantity"] += worked.number_of_days or 0.0
                item["source_payslip_ids"].add(slip.id)
            for input_line in slip.input_line_ids:
                input_type = input_line.input_type_id
                code = (input_type.code if input_type else "") or "NOVEDAD"
                key = ("input", code)
                item = grouped.setdefault(key, {"detail_type": "input", "code": code, "name": input_type.name if input_type else code, "quantity": 0.0, "amount": 0.0, "source_payslip_ids": set()})
                item["quantity"] += 1.0
                item["amount"] += input_line.amount or 0.0
                item["source_payslip_ids"].add(slip.id)
        return [{"period_line_id": period_line.id, "detail_type": item["detail_type"], "code": item["code"], "name": item["name"], "quantity": item["quantity"], "amount": item["amount"], "source_payslip_ids": [(6, 0, list(item["source_payslip_ids"]))]} for item in grouped.values()]

    def action_export_csv(self):
        self.ensure_one()
        if self.state in ("draft", "cancelled"):
            raise UserError(_("Solo puedes exportar un periodo preparado o cerrado."))
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["Empleado", "Identificación", "Departamento", "Cargo", "Básico", "Devengado", "Deducciones", "Neto", "Variación neto", "Aportes empresa", "Ajustes", "Días", "Recibos"])
        for line in self.line_ids:
            writer.writerow([line.employee_id.name, line.employee_id.identification_id or "", line.department_id.name or "", line.job_id.name or "", line.basic_wage, line.gross_wage, line.deduction_total, line.net_wage, line.net_variation, line.employer_cost, sum(self.adjustment_ids.filtered(lambda adjustment: adjustment.employee_id == line.employee_id and adjustment.state in ("approved", "applied")).mapped("amount")), line.worked_days, line.payslip_count])
        attachment = self.env["ir.attachment"].create({"name": "%s.csv" % self.name, "type": "binary", "datas": base64.b64encode(output.getvalue().encode("utf-8-sig")), "res_model": self._name, "res_id": self.id, "mimetype": "text/csv"})
        self.env["l10n.co.payroll.audit"].sudo().create({"company_id": self.company_id.id, "period_id": self.id, "res_model": self._name, "res_id": self.id, "action": "export", "description": _("CSV consolidado generado.")})
        return {"type": "ir.actions.act_url", "url": "/web/content/%s?download=true" % attachment.id, "target": "self"}

    def action_export_pila_csv(self):
        self.ensure_one()
        if self.state in ("draft", "cancelled"):
            raise UserError(_("Solo puedes exportar PILA desde un periodo preparado o cerrado."))
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["Identificación", "Empleado", "Tipo cotizante", "Subtipo", "Días", "IBC referencia", "Novedades", "Estado PILA"])
        for line in self.line_ids.filtered(lambda item: item.pila_reporting_mode == "full"):
            writer.writerow([line.employee_id.identification_id or "", line.employee_id.name, line.pila_type or "", line.pila_subtype or "", line.worked_days, line.ibc_base, ",".join(line.source_payslip_ids.mapped("name")), line.pila_status])
        attachment = self.env["ir.attachment"].create({"name": "%s_PILA.csv" % self.name, "type": "binary", "datas": base64.b64encode(output.getvalue().encode("utf-8-sig")), "res_model": self._name, "res_id": self.id, "mimetype": "text/csv"})
        self.line_ids.filtered(lambda item: item.pila_reporting_mode == "full").sudo().write({"pila_status": "exported"})
        self.env["l10n.co.payroll.audit"].sudo().create({"company_id": self.company_id.id, "period_id": self.id, "res_model": self._name, "res_id": self.id, "action": "pila", "description": _("Exportación PILA CSV generada.")})
        return {"type": "ir.actions.act_url", "url": "/web/content/%s?download=true" % attachment.id, "target": "self"}

    def action_mark_pila_reviewed(self):
        for period in self:
            if period.state in ("draft", "cancelled"):
                raise UserError(_("Solo puedes marcar PILA en un periodo preparado o cerrado."))
            period.line_ids.sudo().write({"pila_status": "reviewed"})
        return self._reload_form()

    def action_print_report(self):
        self.ensure_one()
        return self.env.ref("l10n_co_payroll.action_report_co_payroll_period").report_action(self)

    def _reload_form(self):
        return {"type": "ir.actions.act_window", "name": _("Periodo de nómina"), "res_model": self._name, "view_mode": "form", "res_id": self[:1].id, "target": "current"}

    def unlink(self):
        if any(period.state == "closed" for period in self):
            raise UserError(_("No puedes eliminar un periodo cerrado."))
        return super().unlink()


class CoPayrollPeriodLine(models.Model):
    _name = "l10n.co.payroll.period.line"
    _description = "Resumen de nómina por empleado"
    _order = "employee_id"
    _check_company_auto = True

    period_id = fields.Many2one("l10n.co.payroll.period", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="period_id.company_id", store=True, readonly=True)
    employee_id = fields.Many2one("hr.employee", required=True, readonly=True, index=True)
    department_id = fields.Many2one("hr.department", related="employee_id.department_id", readonly=True)
    job_id = fields.Many2one("hr.job", related="employee_id.job_id", readonly=True)
    contract_id = fields.Many2one("hr.version", string="Contrato", readonly=True)
    source_payslip_ids = fields.Many2many("hr.payslip", "co_payroll_period_line_payslip_rel", "line_id", "payslip_id", string="Recibos fuente", readonly=True)
    detail_ids = fields.One2many("l10n.co.payroll.period.detail", "period_line_id", string="Detalle consolidado", readonly=True)
    rule_result_ids = fields.One2many("l10n.co.payroll.period.rule.result", "period_line_id", string="Cálculo por reglas", readonly=True)
    payslip_count = fields.Integer(compute="_compute_payslip_count", string="Recibos")
    currency_id = fields.Many2one(related="period_id.currency_id", readonly=True)
    basic_wage = fields.Monetary(string="Salario básico", currency_field="currency_id", readonly=True)
    gross_wage = fields.Monetary(string="Devengado", currency_field="currency_id", readonly=True)
    deduction_total = fields.Monetary(string="Deducciones", currency_field="currency_id", readonly=True)
    net_wage = fields.Monetary(string="Neto", currency_field="currency_id", readonly=True)
    employer_cost = fields.Monetary(string="Aportes empresa", currency_field="currency_id", readonly=True)
    worked_days = fields.Float(string="Días", readonly=True)
    worked_hours = fields.Float(string="Horas", readonly=True)
    overtime_day_hours = fields.Float(string="Horas extra diurnas", readonly=True)
    overtime_night_hours = fields.Float(string="Horas extra nocturnas", readonly=True)
    night_hours = fields.Float(string="Horas nocturnas", readonly=True)
    holiday_hours = fields.Float(string="Horas dominicales/festivas", readonly=True)
    ibc_base = fields.Monetary(string="IBC referencia", currency_field="currency_id", readonly=True)
    salary_mode = fields.Selection([("ordinary", "Salario ordinario"), ("integral", "Salario integral")], string="Modalidad salarial", readonly=True)
    social_ibc_base = fields.Monetary(string="IBC legal PILA", currency_field="currency_id", readonly=True)
    health_employee = fields.Monetary(string="Salud empleado", currency_field="currency_id", readonly=True)
    health_employer = fields.Monetary(string="Salud empleador", currency_field="currency_id", readonly=True)
    pension_employee = fields.Monetary(string="Pensión empleado", currency_field="currency_id", readonly=True)
    pension_employer = fields.Monetary(string="Pensión empleador", currency_field="currency_id", readonly=True)
    solidarity_rate = fields.Float(string="Fondo solidaridad (%)", readonly=True)
    solidarity_employee = fields.Monetary(string="Fondo solidaridad", currency_field="currency_id", readonly=True)
    arl_employer = fields.Monetary(string="ARL empleador", currency_field="currency_id", readonly=True)
    ccf_employer = fields.Monetary(string="Caja compensación", currency_field="currency_id", readonly=True)
    sena_employer = fields.Monetary(string="SENA", currency_field="currency_id", readonly=True)
    icbf_employer = fields.Monetary(string="ICBF", currency_field="currency_id", readonly=True)
    social_employee_total = fields.Monetary(string="Aportes empleado calculados", currency_field="currency_id", readonly=True)
    social_employer_total = fields.Monetary(string="Aportes empleador calculados", currency_field="currency_id", readonly=True)
    transport_base = fields.Monetary(string="Auxilio transporte base", currency_field="currency_id", readonly=True)
    provision_severance_base = fields.Monetary(string="Base cesantías", currency_field="currency_id", readonly=True)
    provision_vacation_base = fields.Monetary(string="Base vacaciones", currency_field="currency_id", readonly=True)
    provision_bonus_base = fields.Monetary(string="Base prima", currency_field="currency_id", readonly=True)
    novelty_count = fields.Integer(string="Novedades", readonly=True)
    novelty_days = fields.Float(string="Días con novedad", readonly=True)
    pila_novelty_codes = fields.Char(string="Novedades PILA", readonly=True, help="Códigos de novedad aplicados al periodo: ING, RET, VSP, VST, SLN, IGE, LMA, VAC, IRL o VCT.")
    adjustment_total = fields.Monetary(string="Ajustes", currency_field="currency_id", readonly=True)
    loan_deduction = fields.Monetary(string="Cuotas de préstamos", currency_field="currency_id", readonly=True)
    embargo_deduction = fields.Monetary(string="Embargos", currency_field="currency_id", readonly=True)
    additional_deduction_total = fields.Monetary(string="Descuentos adicionales", compute="_compute_additional_deductions", currency_field="currency_id", readonly=True)
    net_after_deductions = fields.Monetary(string="Neto real a pagar", compute="_compute_additional_deductions", currency_field="currency_id", readonly=True)
    absence_days = fields.Float(string="Días de ausencia", readonly=True)
    pila_status = fields.Selection([("pending", "Pendiente"), ("reviewed", "Revisado"), ("exported", "Exportado")], string="Estado PILA", default="pending", readonly=True)
    pila_reporting_mode = fields.Selection([
        ("full", "Reportar PILA"),
        ("manual", "Reporte externo"),
        ("not_applicable", "No aplica"),
        ("missing", "Sin perfil"),
    ], string="Cobertura PILA", default="missing", readonly=True)
    pila_manual_reference = fields.Char(string="Referencia PILA externa", readonly=True)
    pila_type = fields.Char(string="Tipo cotizante PILA", default="01", readonly=True)
    pila_subtype = fields.Char(string="Subtipo PILA", default="0", readonly=True)
    social_profile_id = fields.Many2one("l10n.co.payroll.social", string="Perfil PILA", readonly=True)
    eps_code = fields.Char(string="EPS", readonly=True)
    pension_code = fields.Char(string="AFP", readonly=True)
    arl_code = fields.Char(string="ARL", readonly=True)
    ccf_code = fields.Char(string="Caja", readonly=True)
    risk_class = fields.Selection([("I", "I"), ("II", "II"), ("III", "III"), ("IV", "IV"), ("V", "V")], string="Riesgo", readonly=True)
    previous_net_wage = fields.Monetary(string="Neto anterior", currency_field="currency_id", readonly=True)
    cost_center_id = fields.Many2one("l10n.co.payroll.cost.center", string="Centro de costo", readonly=True)
    net_variation = fields.Monetary(string="Variación neto", currency_field="currency_id", readonly=True)
    net_variation_pct = fields.Float(string="Variación %", compute="_compute_variation", readonly=True)
    comparison_state = fields.Selection([("new", "Nuevo"), ("changed", "Cambió"), ("unchanged", "Sin cambio")], string="Comparación", readonly=True)

    @api.depends("source_payslip_ids")
    def _compute_payslip_count(self):
        for line in self:
            line.payslip_count = len(line.source_payslip_ids)

    @api.depends("previous_net_wage", "net_variation")
    def _compute_variation(self):
        for line in self:
            line.net_variation_pct = (line.net_variation / line.previous_net_wage * 100) if line.previous_net_wage else 0.0

    @api.depends("loan_deduction", "embargo_deduction", "net_wage")
    def _compute_additional_deductions(self):
        for line in self:
            line.additional_deduction_total = line.loan_deduction + line.embargo_deduction
            line.net_after_deductions = max(line.net_wage - line.additional_deduction_total, 0.0)

    def action_open_payslips(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": _("Recibos de %s") % self.employee_id.name, "res_model": "hr.payslip", "view_mode": "list,form", "domain": [("id", "in", self.source_payslip_ids.ids)], "context": {"create": False}}


class CoPayrollPeriodDetail(models.Model):
    _name = "l10n.co.payroll.period.detail"
    _description = "Detalle agrupado del consolidado"
    _order = "detail_type, code, id"
    _check_company_auto = True

    period_line_id = fields.Many2one("l10n.co.payroll.period.line", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="period_line_id.company_id", store=True, readonly=True)
    detail_type = fields.Selection([
        ("rule", "Concepto salarial"),
        ("worked_day", "Día trabajado"),
        ("input", "Novedad / entrada"),
    ], string="Tipo", required=True, readonly=True)
    code = fields.Char(string="Código", required=True, readonly=True)
    name = fields.Char(string="Detalle", required=True, readonly=True)
    quantity = fields.Float(string="Cantidad", readonly=True)
    amount = fields.Monetary(string="Valor", currency_field="currency_id", readonly=True)
    currency_id = fields.Many2one(related="period_line_id.currency_id", readonly=True)
    source_payslip_ids = fields.Many2many("hr.payslip", "co_payroll_period_detail_payslip_rel", "detail_id", "payslip_id", string="Recibos fuente", readonly=True)


class CoPayrollPeriodIssue(models.Model):
    _name = "l10n.co.payroll.period.issue"
    _description = "Hallazgo de validación de nómina"
    _order = "severity desc, id"
    _check_company_auto = True

    period_id = fields.Many2one("l10n.co.payroll.period", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="period_id.company_id", store=True, readonly=True)
    severity = fields.Selection([("error", "Bloqueante"), ("warning", "Advertencia"), ("info", "Información")], required=True, default="warning")
    code = fields.Char(string="Código", required=True, readonly=True)
    message = fields.Text(string="Detalle", required=True, readonly=True)
    employee_id = fields.Many2one("hr.employee", string="Empleado", readonly=True)
    payslip_id = fields.Many2one("hr.payslip", string="Recibo", readonly=True)
    resolved = fields.Boolean(string="Revisado")


class CoPayrollPeriodDiagnostic(models.Model):
    _name = "l10n.co.payroll.period.diagnostic"
    _description = "Diagnóstico integral del periodo de nómina"
    _order = "resolved, severity desc, id"
    _check_company_auto = True

    period_id = fields.Many2one("l10n.co.payroll.period", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="period_id.company_id", store=True, readonly=True)
    period_line_id = fields.Many2one("l10n.co.payroll.period.line", string="Línea consolidada", readonly=True, ondelete="cascade")
    employee_id = fields.Many2one("hr.employee", string="Empleado", readonly=True)
    payslip_id = fields.Many2one("hr.payslip", string="Recibo", readonly=True)
    diagnostic_type = fields.Selection([
        ("payroll", "Nómina"), ("pila", "PILA"), ("dian", "DIAN"), ("accounting", "Contabilidad"), ("payment", "Pagos"),
    ], string="Área", required=True, readonly=True)
    severity = fields.Selection([
        ("error", "Bloqueante"), ("warning", "Advertencia"), ("info", "Información"),
    ], string="Nivel", required=True, default="warning", readonly=True)
    code = fields.Char(string="Código", required=True, readonly=True)
    message = fields.Text(string="Detalle", required=True, readonly=True)
    resolved = fields.Boolean(string="Revisado")
    resolution_notes = fields.Text(string="Notas de resolución")
    created_at = fields.Datetime(string="Generado el", default=fields.Datetime.now, readonly=True)

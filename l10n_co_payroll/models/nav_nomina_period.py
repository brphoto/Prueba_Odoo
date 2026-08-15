import base64
import csv
import io
import time
from collections import defaultdict

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


VALID_PAYSLIP_STATES = ("validated", "paid", "done")


class NavNominaPeriod(models.Model):
    _name = "nav.nomina.period"
    _description = "Periodo operativo de nómina"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_from desc, id desc"
    _check_company_auto = True

    name = fields.Char(string="Referencia", required=True, copy=False, default=lambda self: self.env["ir.sequence"].next_by_code("nav.nomina.period") or _("Nuevo"), tracking=True)
    company_id = fields.Many2one("res.company", string="Compañía", required=True, default=lambda self: self.env.company, index=True, tracking=True)
    period_type = fields.Selection([("monthly", "Mensual"), ("biweekly", "Quincenal"), ("weekly", "Semanal"), ("off_cycle", "Extraordinario")], string="Frecuencia", required=True, default="monthly", tracking=True)
    date_from = fields.Date(string="Desde", required=True, default=lambda self: fields.Date.context_today(self).replace(day=1), tracking=True, index=True)
    date_to = fields.Date(string="Hasta", required=True, default=lambda self: fields.Date.context_today(self) + relativedelta(day=31), tracking=True, index=True)
    payment_date = fields.Date(string="Fecha de pago", tracking=True)
    employee_ids = fields.Many2many("hr.employee", "nav_nomina_period_employee_rel", "period_id", "employee_id", string="Empleados a incluir", help="Déjalo vacío para incluir todos los empleados con recibos en el periodo.")
    department_ids = fields.Many2many("hr.department", "nav_nomina_period_department_rel", "period_id", "department_id", string="Departamentos")
    job_ids = fields.Many2many("hr.job", "nav_nomina_period_job_rel", "period_id", "job_id", string="Cargos")
    structure_ids = fields.Many2many("hr.payroll.structure", "nav_nomina_period_structure_rel", "period_id", "structure_id", string="Estructuras salariales")
    payslip_run_ids = fields.Many2many("hr.payslip.run", "nav_nomina_period_run_rel", "period_id", "run_id", string="Lotes de nómina")
    parameter_id = fields.Many2one("nav.nomina.parameter", string="Parámetros del año", domain="[('company_id', '=', company_id)]", help="Configuración anual de referencia. Los valores son editables y no calculan automáticamente el recibo.")
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
    line_ids = fields.One2many("nav.nomina.period.line", "period_id", string="Resumen por empleado", copy=False)
    issue_ids = fields.One2many("nav.nomina.period.issue", "period_id", string="Detalle de validaciones", copy=False)
    novelty_ids = fields.One2many("nav.nomina.novelty", "period_id", string="Detalle de novedades", copy=False)
    adjustment_ids = fields.One2many("nav.nomina.adjustment", "period_id", string="Ajustes", copy=False)
    previous_period_id = fields.Many2one("nav.nomina.period", string="Periodo anterior", compute="_compute_previous_period")
    state = fields.Selection([("draft", "Borrador"), ("ready", "Preparado"), ("closed", "Cerrado"), ("cancelled", "Cancelado")], string="Estado", default="draft", required=True, copy=False, tracking=True, index=True)
    note = fields.Text(string="Notas")
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)
    payslip_count = fields.Integer(string="Recibos", compute="_compute_metrics")
    employee_count = fields.Integer(string="Empleados encontrados", compute="_compute_metrics")
    unvalidated_count = fields.Integer(string="Pendientes", compute="_compute_metrics")
    issue_count = fields.Integer(string="Hallazgos", compute="_compute_issue_metrics")
    blocking_issue_count = fields.Integer(string="Bloqueantes", compute="_compute_issue_metrics")
    warning_issue_count = fields.Integer(string="Advertencias", compute="_compute_issue_metrics")
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
    audit_event_ids = fields.One2many("nav.nomina.audit", "period_id", string="Trazabilidad", readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            company_id = vals.get("company_id") or self.env.company.id
            date_from = fields.Date.to_date(vals.get("date_from")) or fields.Date.context_today(self)
            parameter = self.env["nav.nomina.parameter"].search([
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
            duplicate = self.search([("id", "!=", period.id), ("company_id", "=", period.company_id.id), ("date_from", "=", period.date_from), ("date_to", "=", period.date_to), ("state", "!=", "cancelled")], limit=1)
            if duplicate:
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

    @api.depends("gross_total", "parameter_id.severance_rate", "parameter_id.severance_interest_rate", "parameter_id.vacation_rate", "parameter_id.bonus_rate")
    def _compute_provisions(self):
        for period in self:
            parameter = period.parameter_id
            gross = period.gross_total
            period.provision_severance = gross * (parameter.severance_rate / 100.0) if parameter else 0.0
            period.provision_severance_interest = period.provision_severance * (parameter.severance_interest_rate / 100.0) if parameter else 0.0
            period.provision_vacation = gross * (parameter.vacation_rate / 100.0) if parameter else 0.0
            period.provision_bonus = gross * (parameter.bonus_rate / 100.0) if parameter else 0.0

    @api.model
    def _summarize_payslips(self, payslips, parameter=None):
        values = {"basic_wage": sum(payslips.mapped("basic_wage")), "gross_wage": sum(payslips.mapped("gross_wage")) if "gross_wage" in payslips._fields else 0.0, "deduction_total": 0.0, "net_wage": sum(payslips.mapped("net_wage")), "employer_cost": sum(payslips.mapped("employer_cost")) if "employer_cost" in payslips._fields else 0.0, "worked_days": 0.0, "worked_hours": 0.0, "ibc_base": 0.0}
        category_totals = defaultdict(float)
        mapped_totals = defaultdict(float)
        mappings = {mapping.code: mapping for mapping in parameter.rule_mapping_ids.filtered("active")} if parameter else {}
        for slip in payslips:
            for line in slip.line_ids:
                category_totals[(getattr(line.category_id, "code", "") or "").upper()] += line.total or 0.0
                rule_code = getattr(getattr(line, "salary_rule_id", False), "code", False)
                mapping = mappings.get(rule_code)
                if mapping:
                    mapped_totals[mapping.concept_type] += line.total or 0.0
                    if mapping.include_in_ibc:
                        mapped_totals["ibc"] += line.total or 0.0
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
        return values

    def _run_validation(self, payslips=None):
        Issue = self.env["nav.nomina.period.issue"]
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
                if not self.env["nav.nomina.social"].get_for_employee(employee, period.date_from):
                    vals_list.append({"period_id": period.id, "severity": "warning", "code": "NO_SOCIAL_PROFILE", "message": _("%s no tiene un perfil PILA vigente para el periodo.") % employee.name, "employee_id": employee.id, "payslip_id": slip.id})
                if not employee.identification_id:
                    vals_list.append({"period_id": period.id, "severity": "warning", "code": "NO_IDENTIFICATION", "message": _("%s no tiene identificación configurada.") % employee.name, "employee_id": employee.id, "payslip_id": slip.id})
                if slip.state not in VALID_PAYSLIP_STATES:
                    vals_list.append({"period_id": period.id, "severity": "error", "code": "UNVALIDATED", "message": _("El recibo %s no está validado.") % slip.display_name, "employee_id": employee.id, "payslip_id": slip.id})
                if not getattr(slip, "version_id", False):
                    vals_list.append({"period_id": period.id, "severity": "error", "code": "NO_CONTRACT", "message": _("%s no tiene contrato/version vigente en el recibo.") % employee.name, "employee_id": employee.id, "payslip_id": slip.id})
                summary = self._summarize_payslips(slip, period.parameter_id)
                if summary["basic_wage"] <= 0:
                    vals_list.append({"period_id": period.id, "severity": "warning", "code": "ZERO_BASIC", "message": _("El salario básico de %s es cero o no está informado.") % employee.name, "employee_id": employee.id, "payslip_id": slip.id})
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
            period.line_ids.sudo().unlink()
            by_employee = defaultdict(lambda: self.env["hr.payslip"])
            for payslip in payslips:
                by_employee[payslip.employee_id.id] |= payslip
            previous_lines = {line.employee_id.id: line for line in period.previous_period_id.line_ids}
            line_model = self.env["nav.nomina.period.line"].sudo()
            for employee_id, employee_payslips in by_employee.items():
                employee = employee_payslips[0].employee_id
                social = self.env["nav.nomina.social"].get_for_employee(employee, period.date_from)
                summary = self._summarize_payslips(employee_payslips, period.parameter_id)
                previous = previous_lines.get(employee_id)
                previous_net = previous.net_wage if previous else 0.0
                variation = summary["net_wage"] - previous_net
                novelties = period.novelty_ids.filtered(lambda novelty: novelty.employee_id == employee and novelty.state in ("approved", "applied"))
                adjustments = period.adjustment_ids.filtered(lambda adjustment: adjustment.employee_id == employee and adjustment.state in ("approved", "applied"))
                line_model.create({"period_id": period.id, "employee_id": employee_id, "contract_id": employee_payslips[0].version_id.id if employee_payslips[0].version_id else False, "source_payslip_ids": [(6, 0, employee_payslips.ids)], "social_profile_id": social.id, "pila_type": social.contributor_type if social else "01", "pila_subtype": social.contributor_subtype if social else "0", "eps_code": social.eps_code if social else False, "pension_code": social.pension_code if social else False, "arl_code": social.arl_code if social else False, "ccf_code": social.ccf_code if social else False, "risk_class": social.risk_class if social else False, "novelty_count": len(novelties), "novelty_days": sum(novelties.mapped("days")), "adjustment_total": sum(adjustments.mapped("amount")), "pila_status": "pending", "previous_net_wage": previous_net, "net_variation": variation, "comparison_state": "new" if not previous else ("changed" if abs(variation) > 0.01 else "unchanged"), **summary})
            period._run_validation(payslips)
            period.novelty_ids.filtered(lambda novelty: novelty.state == "approved").write({"state": "applied"})
            period.write({"state": "ready", "approval_state": "not_required" if period.approval_mode == "none" else "pending", "approval_by": False, "approval_at": False, "second_approval_by": False, "second_approval_at": False, "rejection_reason": False, "prepared_by": self.env.user.id, "prepared_at": fields.Datetime.now(), "processing_seconds": time.monotonic() - started_at, "last_run_count": len(payslips)})
            self.env["nav.nomina.audit"].sudo().create({"company_id": period.company_id.id, "res_model": period._name, "res_id": period.id, "action": "prepare", "description": _("Periodo preparado con %s recibos.") % len(payslips)})
        return self._reload_form()

    def action_run_checks(self):
        self._run_validation()
        self.env["nav.nomina.audit"].sudo().create([{"company_id": period.company_id.id, "period_id": period.id, "res_model": period._name, "res_id": period.id, "action": "validate", "description": _("Validaciones ejecutadas.")} for period in self])
        return self._reload_form()

    def action_approve(self):
        if not (self.env.su or self.env.user._is_admin() or self.env.user.has_group("l10n_co_payroll.group_nav_nomina_manager")):
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
            self.env["nav.nomina.audit"].sudo().create({"company_id": period.company_id.id, "period_id": period.id, "res_model": period._name, "res_id": period.id, "action": "approve", "description": _("Aprobación registrada en modo %s.") % period.approval_mode})
        return self._reload_form()

    def action_reject_approval(self):
        if not (self.env.su or self.env.user._is_admin() or self.env.user.has_group("l10n_co_payroll.group_nav_nomina_manager")):
            raise UserError(_("Solo un supervisor puede rechazar el cierre."))
        self.write({"approval_state": "rejected", "rejection_reason": _("Rechazado por %s") % self.env.user.name, "second_approval_by": False, "second_approval_at": False})
        self.env["nav.nomina.audit"].sudo().create([{"company_id": period.company_id.id, "period_id": period.id, "res_model": period._name, "res_id": period.id, "action": "reject", "description": period.rejection_reason or _("Aprobación rechazada.")} for period in self])
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
            if not (self.env.su or self.env.user._is_admin() or self.env.user.has_group("l10n_co_payroll.group_nav_nomina_manager")):
                raise UserError(_("Solo un supervisor puede cerrar un periodo."))
            period.write({"state": "closed", "closed_by": self.env.user.id, "closed_at": fields.Datetime.now()})
            self.env["nav.nomina.audit"].sudo().create({"company_id": period.company_id.id, "period_id": period.id, "res_model": period._name, "res_id": period.id, "action": "close", "description": _("Periodo cerrado.")})
        return self._reload_form()

    def action_set_draft(self):
        for period in self:
            if period.state == "closed":
                raise UserError(_("Un periodo cerrado no se puede devolver a borrador."))
            period.write({"state": "draft", "approval_state": "not_required" if period.approval_mode == "none" else "pending", "approval_by": False, "approval_at": False, "second_approval_by": False, "second_approval_at": False})

    def action_cancel(self):
        if not (self.env.su or self.env.user._is_admin() or self.env.user.has_group("l10n_co_payroll.group_nav_nomina_manager")):
            raise UserError(_("Solo un supervisor puede cancelar un periodo."))
        if any(period.state == "closed" for period in self):
            raise UserError(_("Un periodo cerrado no se puede cancelar."))
        self.write({"state": "cancelled"})
        self.env["nav.nomina.audit"].sudo().create([{"company_id": period.company_id.id, "period_id": period.id, "res_model": period._name, "res_id": period.id, "action": "cancel", "description": _("Periodo cancelado.")} for period in self])

    def action_open_payslips(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": _("Recibos del periodo"), "res_model": "hr.payslip", "view_mode": "list,form", "domain": [("id", "in", self.source_payslip_ids.ids)], "context": {"create": False}}

    def action_open_lines(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": _("Resumen por empleado"), "res_model": "nav.nomina.period.line", "view_mode": "list,form", "domain": [("period_id", "=", self.id)], "context": {"create": False, "delete": False}}

    def action_open_issues(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": _("Hallazgos de validación"), "res_model": "nav.nomina.period.issue", "view_mode": "list,form", "domain": [("period_id", "=", self.id)], "context": {"create": False, "delete": False}}

    def action_open_novelties(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": _("Novedades del periodo"), "res_model": "nav.nomina.novelty", "view_mode": "list,form", "domain": [("period_id", "=", self.id)], "context": {"create": False}}

    def action_open_previous_period(self):
        self.ensure_one()
        if not self.previous_period_id:
            raise UserError(_("No hay un periodo anterior cerrado para comparar."))
        return {"type": "ir.actions.act_window", "name": _("Periodo anterior"), "res_model": self._name, "view_mode": "form", "res_id": self.previous_period_id.id}

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
        self.env["nav.nomina.audit"].sudo().create({"company_id": self.company_id.id, "period_id": self.id, "res_model": self._name, "res_id": self.id, "action": "export", "description": _("CSV consolidado generado.")})
        return {"type": "ir.actions.act_url", "url": "/web/content/%s?download=true" % attachment.id, "target": "self"}

    def action_export_pila_csv(self):
        self.ensure_one()
        if self.state in ("draft", "cancelled"):
            raise UserError(_("Solo puedes exportar PILA desde un periodo preparado o cerrado."))
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["Identificación", "Empleado", "Tipo cotizante", "Subtipo", "Días", "IBC referencia", "Novedades", "Estado PILA"])
        for line in self.line_ids:
            writer.writerow([line.employee_id.identification_id or "", line.employee_id.name, line.pila_type or "", line.pila_subtype or "", line.worked_days, line.ibc_base, ",".join(line.source_payslip_ids.mapped("name")), line.pila_status])
        attachment = self.env["ir.attachment"].create({"name": "%s_PILA.csv" % self.name, "type": "binary", "datas": base64.b64encode(output.getvalue().encode("utf-8-sig")), "res_model": self._name, "res_id": self.id, "mimetype": "text/csv"})
        self.line_ids.sudo().write({"pila_status": "exported"})
        self.env["nav.nomina.audit"].sudo().create({"company_id": self.company_id.id, "period_id": self.id, "res_model": self._name, "res_id": self.id, "action": "pila", "description": _("Exportación PILA CSV generada.")})
        return {"type": "ir.actions.act_url", "url": "/web/content/%s?download=true" % attachment.id, "target": "self"}

    def action_mark_pila_reviewed(self):
        for period in self:
            if period.state in ("draft", "cancelled"):
                raise UserError(_("Solo puedes marcar PILA en un periodo preparado o cerrado."))
            period.line_ids.sudo().write({"pila_status": "reviewed"})
        return self._reload_form()

    def action_print_report(self):
        self.ensure_one()
        return self.env.ref("l10n_co_payroll.action_report_nav_nomina_period").report_action(self)

    def _reload_form(self):
        return {"type": "ir.actions.act_window", "name": _("Periodo de nómina"), "res_model": self._name, "view_mode": "form", "res_id": self[:1].id, "target": "current"}

    def unlink(self):
        if any(period.state == "closed" for period in self):
            raise UserError(_("No puedes eliminar un periodo cerrado."))
        return super().unlink()


class NavNominaPeriodLine(models.Model):
    _name = "nav.nomina.period.line"
    _description = "Resumen de nómina por empleado"
    _order = "employee_id"
    _check_company_auto = True

    period_id = fields.Many2one("nav.nomina.period", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="period_id.company_id", store=True, readonly=True)
    employee_id = fields.Many2one("hr.employee", required=True, readonly=True, index=True)
    department_id = fields.Many2one("hr.department", related="employee_id.department_id", readonly=True)
    job_id = fields.Many2one("hr.job", related="employee_id.job_id", readonly=True)
    contract_id = fields.Many2one("hr.version", string="Contrato", readonly=True)
    source_payslip_ids = fields.Many2many("hr.payslip", "nav_nomina_period_line_payslip_rel", "line_id", "payslip_id", string="Recibos fuente", readonly=True)
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
    novelty_count = fields.Integer(string="Novedades", readonly=True)
    novelty_days = fields.Float(string="Días con novedad", readonly=True)
    adjustment_total = fields.Monetary(string="Ajustes", currency_field="currency_id", readonly=True)
    pila_status = fields.Selection([("pending", "Pendiente"), ("reviewed", "Revisado"), ("exported", "Exportado")], string="Estado PILA", default="pending", readonly=True)
    pila_type = fields.Char(string="Tipo cotizante PILA", default="01", readonly=True)
    pila_subtype = fields.Char(string="Subtipo PILA", default="0", readonly=True)
    social_profile_id = fields.Many2one("nav.nomina.social", string="Perfil PILA", readonly=True)
    eps_code = fields.Char(string="EPS", readonly=True)
    pension_code = fields.Char(string="AFP", readonly=True)
    arl_code = fields.Char(string="ARL", readonly=True)
    ccf_code = fields.Char(string="Caja", readonly=True)
    risk_class = fields.Selection([("I", "I"), ("II", "II"), ("III", "III"), ("IV", "IV"), ("V", "V")], string="Riesgo", readonly=True)
    previous_net_wage = fields.Monetary(string="Neto anterior", currency_field="currency_id", readonly=True)
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

    def action_open_payslips(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": _("Recibos de %s") % self.employee_id.name, "res_model": "hr.payslip", "view_mode": "list,form", "domain": [("id", "in", self.source_payslip_ids.ids)], "context": {"create": False}}


class NavNominaPeriodIssue(models.Model):
    _name = "nav.nomina.period.issue"
    _description = "Hallazgo de validación de nómina"
    _order = "severity desc, id"
    _check_company_auto = True

    period_id = fields.Many2one("nav.nomina.period", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="period_id.company_id", store=True, readonly=True)
    severity = fields.Selection([("error", "Bloqueante"), ("warning", "Advertencia"), ("info", "Información")], required=True, default="warning")
    code = fields.Char(string="Código", required=True, readonly=True)
    message = fields.Text(string="Detalle", required=True, readonly=True)
    employee_id = fields.Many2one("hr.employee", string="Empleado", readonly=True)
    payslip_id = fields.Many2one("hr.payslip", string="Recibo", readonly=True)
    resolved = fields.Boolean(string="Revisado")

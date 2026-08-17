from datetime import date
import base64
import csv
import hashlib
import io

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class CoPayrollCalendar(models.Model):
    _name = "l10n.co.payroll.calendar"
    _description = "Calendario operativo de nómina"
    _order = "date_from, payment_date"
    _check_company_auto = True

    name = fields.Char(required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    year = fields.Integer(required=True, default=lambda self: fields.Date.context_today(self).year)
    period_type = fields.Selection([("monthly", "Mensual"), ("biweekly", "Quincenal"), ("weekly", "Semanal"), ("off_cycle", "Extraordinario")], string="Frecuencia", required=True, default="monthly")
    period_id = fields.Many2one("l10n.co.payroll.period", string="Periodo creado", readonly=True, copy=False)
    date_from = fields.Date(required=True)
    date_to = fields.Date(required=True)
    payment_date = fields.Date(required=True)
    cutoff_date = fields.Date(string="Fecha de corte")
    state = fields.Selection([("planned", "Planeado"), ("processed", "Procesado"), ("cancelled", "Cancelado")], default="planned", required=True)
    notes = fields.Text()

    @api.constrains("date_from", "date_to", "payment_date")
    def _check_dates(self):
        for record in self:
            if record.date_from > record.date_to:
                raise ValidationError(_("La fecha inicial no puede superar la final."))
            if record.payment_date < record.date_from:
                raise ValidationError(_("La fecha de pago no puede ser anterior al inicio del periodo."))

    def action_create_period(self):
        for record in self:
            if record.state != "planned":
                continue
            period = self.env["l10n.co.payroll.period"].create({
                "company_id": record.company_id.id,
                "period_type": record.period_type or "monthly",
                "date_from": record.date_from,
                "date_to": record.date_to,
                "payment_date": record.payment_date,
            })
            record.write({"period_id": period.id, "state": "processed"})
            self.env["l10n.co.payroll.audit"].sudo().create({"company_id": record.company_id.id, "period_id": period.id, "res_model": record._name, "res_id": record.id, "action": "other", "description": _("Periodo creado desde calendario.")})
        return True


class CoPayrollNoveltyImport(models.Model):
    _name = "l10n.co.payroll.novelty.import"
    _description = "Importación masiva de novedades"
    _order = "create_date desc"
    _check_company_auto = True

    name = fields.Char(required=True, default=lambda self: _("Importación de novedades"))
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    period_id = fields.Many2one("l10n.co.payroll.period", required=True, ondelete="restrict")
    import_file = fields.Binary(string="Archivo CSV", required=True)
    filename = fields.Char()
    state = fields.Selection([("draft", "Borrador"), ("imported", "Importado"), ("error", "Con errores")], default="draft", required=True)
    imported_count = fields.Integer(readonly=True)
    error_message = fields.Text(readonly=True)

    def action_import(self):
        for record in self:
            if record.period_id.state in ("closed", "cancelled"):
                raise UserError(_("No puedes importar novedades en un periodo cerrado."))
            raw = base64.b64decode(record.import_file).decode("utf-8-sig", errors="replace")
            reader = csv.DictReader(io.StringIO(raw), delimiter=";")
            errors = []
            values = []
            for number, row in enumerate(reader, start=2):
                identification = (row.get("identificacion") or row.get("documento") or "").strip()
                employee = self.env["hr.employee"].search([("identification_id", "=", identification), ("company_id", "=", record.company_id.id)], limit=1)
                try:
                    days = float((row.get("dias") or row.get("days") or "0").replace(",", "."))
                    amount = float((row.get("valor") or row.get("amount") or "0").replace(",", "."))
                except ValueError:
                    errors.append(_("Línea %s: días o valor inválido.") % number)
                    continue
                if not employee:
                    errors.append(_("Línea %s: no existe empleado con identificación %s.") % (number, identification))
                    continue
                values.append({"period_id": record.period_id.id, "employee_id": employee.id, "novelty_type": row.get("tipo") or "vst", "date_from": row.get("desde") or record.period_id.date_from, "date_to": row.get("hasta") or record.period_id.date_to, "days": days, "amount": amount, "notes": row.get("observaciones") or "Importada masivamente."})
            if values:
                self.env["l10n.co.payroll.novelty"].create(values)
            record.write({"state": "error" if errors else "imported", "imported_count": len(values), "error_message": "\n".join(errors)})
        return True


class CoPayrollValidationRule(models.Model):
    _name = "l10n.co.payroll.validation.rule"
    _description = "Regla configurable de validación"
    _order = "sequence, name"
    _check_company_auto = True

    name = fields.Char(required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    sequence = fields.Integer(default=10)
    code = fields.Selection([
        ("identification", "Identificación del empleado"),
        ("social_profile", "Perfil PILA vigente"),
        ("bank_account", "Cuenta bancaria"),
        ("minimum_net", "Neto mínimo"),
        ("deduction_ratio", "Límite de deducciones"),
    ], required=True)
    severity = fields.Selection([("error", "Bloqueante"), ("warning", "Advertencia"), ("info", "Información")], default="warning", required=True)
    threshold = fields.Float(string="Umbral")
    active = fields.Boolean(default=True)
    notes = fields.Text()

    _company_code_unique = models.Constraint("unique(company_id, code)", "Ya existe esta regla para la compañía.")


class CoPayrollTask(models.Model):
    _name = "l10n.co.payroll.task"
    _description = "Tarea operativa de nómina"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "priority desc, deadline, id"
    _check_company_auto = True

    name = fields.Char(required=True, tracking=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    period_id = fields.Many2one("l10n.co.payroll.period", ondelete="cascade", index=True)
    employee_id = fields.Many2one("hr.employee", index=True)
    issue_id = fields.Many2one("l10n.co.payroll.period.issue", ondelete="set null")
    task_type = fields.Selection([("validation", "Validación"), ("approval", "Aprobación"), ("bank", "Bancaria"), ("pila", "PILA"), ("accounting", "Contabilidad"), ("document", "Documento"), ("other", "Otra")], required=True, default="validation")
    priority = fields.Selection([("0", "Normal"), ("1", "Alta"), ("2", "Urgente")], default="0", required=True)
    state = fields.Selection([("open", "Pendiente"), ("in_progress", "En curso"), ("done", "Resuelta"), ("cancelled", "Cancelada")], default="open", required=True, tracking=True)
    deadline = fields.Date()
    description = fields.Text()
    assigned_user_id = fields.Many2one("res.users", string="Responsable", default=lambda self: self.env.user)
    resolved_by = fields.Many2one("res.users", readonly=True)
    resolved_at = fields.Datetime(readonly=True)

    def action_start(self):
        self.write({"state": "in_progress"})

    def action_done(self):
        self.write({"state": "done", "resolved_by": self.env.user.id, "resolved_at": fields.Datetime.now()})

    def action_cancel(self):
        self.write({"state": "cancelled"})


class CoPayrollChecklist(models.Model):
    _name = "l10n.co.payroll.checklist"
    _description = "Checklist de cierre de nómina"
    _order = "sequence, id"
    _check_company_auto = True

    name = fields.Char(required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    period_id = fields.Many2one("l10n.co.payroll.period", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)
    required = fields.Boolean(default=True)
    state = fields.Selection([("pending", "Pendiente"), ("done", "Completado"), ("skipped", "Omitido")], default="pending", required=True)
    checked_by = fields.Many2one("res.users", readonly=True)
    checked_at = fields.Datetime(readonly=True)
    notes = fields.Text()

    def action_done(self):
        self.write({"state": "done", "checked_by": self.env.user.id, "checked_at": fields.Datetime.now()})

    def action_skip(self):
        self.write({"state": "skipped", "checked_by": self.env.user.id, "checked_at": fields.Datetime.now()})


class CoPayrollSnapshot(models.Model):
    _name = "l10n.co.payroll.snapshot"
    _description = "Copia funcional de periodo"
    _order = "snapshot_date desc, id desc"
    _check_company_auto = True

    name = fields.Char(required=True, copy=False)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    period_id = fields.Many2one("l10n.co.payroll.period", required=True, ondelete="cascade", index=True)
    snapshot_date = fields.Datetime(required=True, default=fields.Datetime.now, readonly=True)
    created_by = fields.Many2one("res.users", required=True, default=lambda self: self.env.user, readonly=True)
    attachment_id = fields.Many2one("ir.attachment", readonly=True, copy=False)
    checksum = fields.Char(readonly=True, copy=False)
    record_count = fields.Integer(readonly=True)
    notes = fields.Text()

    def action_download(self):
        self.ensure_one()
        if not self.attachment_id:
            raise UserError(_("La copia funcional todavía no tiene archivo."))
        return {"type": "ir.actions.act_url", "url": "/web/content/%s?download=true" % self.attachment_id.id, "target": "self"}


class CoPayrollSalaryHistory(models.Model):
    _name = "l10n.co.payroll.salary.history"
    _description = "Historial salarial"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "effective_date desc, id desc"
    _check_company_auto = True

    name = fields.Char(required=True, default=lambda self: _("Cambio salarial"))
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    employee_id = fields.Many2one("hr.employee", required=True, index=True)
    contract_id = fields.Many2one("hr.version", string="Contrato / versión")
    effective_date = fields.Date(required=True, default=fields.Date.context_today)
    previous_wage = fields.Monetary(required=True, currency_field="currency_id")
    new_wage = fields.Monetary(required=True, currency_field="currency_id")
    difference = fields.Monetary(compute="_compute_difference", store=True, currency_field="currency_id")
    reason = fields.Selection([("promotion", "Promoción"), ("increase", "Incremento"), ("legal", "Ajuste legal"), ("correction", "Corrección"), ("other", "Otro")], required=True, default="increase")
    state = fields.Selection([("draft", "Borrador"), ("approved", "Aprobado"), ("applied", "Aplicado"), ("cancelled", "Cancelado")], default="draft", required=True, tracking=True)
    approved_by = fields.Many2one("res.users", readonly=True)
    approved_at = fields.Datetime(readonly=True)
    notes = fields.Text()
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)

    @api.depends("previous_wage", "new_wage")
    def _compute_difference(self):
        for record in self:
            record.difference = record.new_wage - record.previous_wage

    @api.constrains("previous_wage", "new_wage")
    def _check_wage(self):
        for record in self:
            if record.previous_wage < 0 or record.new_wage <= 0:
                raise ValidationError(_("Los salarios deben ser positivos y el anterior no puede ser negativo."))

    def action_approve(self):
        if not (self.env.su or self.env.user._is_admin() or self.env.user.has_group("l10n_co_payroll.group_co_payroll_manager")):
            raise UserError(_("Solo un supervisor puede aprobar cambios salariales."))
        self.write({"state": "approved", "approved_by": self.env.user.id, "approved_at": fields.Datetime.now()})

    def action_apply(self):
        for record in self:
            if record.state != "approved":
                raise UserError(_("El cambio salarial debe estar aprobado."))
            contract = record.contract_id or self.env["hr.version"].search([("employee_id", "=", record.employee_id.id), ("company_id", "=", record.company_id.id)], order="date_version desc, id desc", limit=1)
            if not contract:
                raise UserError(_("El empleado no tiene una versión contractual para aplicar el cambio."))
            if "wage" in contract._fields:
                contract.sudo().write({"wage": record.new_wage})
            record.write({"state": "applied", "contract_id": contract.id})
            self.env["l10n.co.payroll.audit"].sudo().create({"company_id": record.company_id.id, "res_model": record._name, "res_id": record.id, "action": "other", "description": _("Cambio salarial aplicado a %s.") % record.employee_id.name})


class CoPayrollLoan(models.Model):
    _name = "l10n.co.payroll.loan"
    _description = "Préstamo de empleado"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"
    _check_company_auto = True

    name = fields.Char(required=True, default=lambda self: _("Préstamo"), copy=False)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    employee_id = fields.Many2one("hr.employee", required=True, index=True)
    date = fields.Date(required=True, default=fields.Date.context_today)
    amount = fields.Monetary(required=True, currency_field="currency_id")
    balance = fields.Monetary(required=True, currency_field="currency_id")
    installment = fields.Monetary(required=True, string="Cuota", currency_field="currency_id")
    installments_total = fields.Integer(string="Número de cuotas", required=True, default=1)
    installments_paid = fields.Integer(default=0, readonly=True)
    state = fields.Selection([("draft", "Borrador"), ("approved", "Aprobado"), ("active", "Activo"), ("paid", "Pagado"), ("cancelled", "Cancelado")], default="draft", required=True, tracking=True)
    notes = fields.Text()
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)

    @api.constrains("amount", "balance", "installment", "installments_total")
    def _check_values(self):
        for record in self:
            if record.amount <= 0 or record.balance < 0 or record.installment <= 0 or record.installments_total <= 0:
                raise ValidationError(_("El préstamo, saldo y cuota deben ser positivos."))

    def action_approve(self):
        self.write({"state": "approved"})

    def action_activate(self):
        self.write({"state": "active"})

    def action_register_payment(self, amount=None):
        for record in self:
            payment = min(amount or record.installment, record.balance)
            record.write({"balance": record.balance - payment, "installments_paid": record.installments_paid + 1, "state": "paid" if record.balance - payment <= 0 else "active"})


class CoPayrollEmbargo(models.Model):
    _name = "l10n.co.payroll.embargo"
    _description = "Embargo de nómina"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "priority, date desc"
    _check_company_auto = True

    name = fields.Char(required=True, default=lambda self: _("Embargo"), copy=False)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    employee_id = fields.Many2one("hr.employee", required=True, index=True)
    authority = fields.Char(string="Autoridad")
    reference = fields.Char(string="Radicado")
    date = fields.Date(required=True, default=fields.Date.context_today)
    priority = fields.Integer(default=10, help="Menor número = mayor prioridad.")
    mode = fields.Selection([("fixed", "Valor fijo"), ("percentage", "Porcentaje")], required=True, default="fixed")
    amount = fields.Monetary(string="Valor / porcentaje", required=True, currency_field="currency_id")
    balance = fields.Monetary(required=True, currency_field="currency_id")
    state = fields.Selection([("draft", "Borrador"), ("approved", "Aprobado"), ("active", "Activo"), ("paid", "Cumplido"), ("cancelled", "Cancelado")], default="draft", required=True, tracking=True)
    notes = fields.Text()
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)

    @api.constrains("amount", "balance", "mode")
    def _check_amount(self):
        for record in self:
            if record.amount <= 0 or record.balance < 0 or (record.mode == "percentage" and record.amount > 100):
                raise ValidationError(_("El embargo tiene un valor inválido."))

    def action_approve(self):
        self.write({"state": "approved"})

    def action_activate(self):
        self.write({"state": "active"})

    def action_register_payment(self, amount=None):
        for record in self:
            payment = min(amount or record.amount, record.balance)
            record.write({"balance": record.balance - payment, "state": "paid" if record.balance - payment <= 0 else "active"})


class CoPayrollSimulation(models.Model):
    _name = "l10n.co.payroll.simulation"
    _description = "Simulador de nómina"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc"
    _check_company_auto = True

    name = fields.Char(required=True, default=lambda self: _("Simulación"), copy=False)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    date = fields.Date(required=True, default=fields.Date.context_today)
    period_id = fields.Many2one("l10n.co.payroll.period", string="Periodo de referencia")
    employee_ids = fields.Many2many("hr.employee", string="Empleados")
    salary_variation = fields.Float(string="Variación salarial (%)")
    fixed_variation = fields.Monetary(string="Variación fija", currency_field="currency_id")
    employer_rate = fields.Float(string="Costo empresa adicional (%)")
    state = fields.Selection([("draft", "Borrador"), ("calculated", "Calculada"), ("applied", "Aplicada"), ("cancelled", "Cancelada")], default="draft", required=True, tracking=True)
    line_ids = fields.One2many("l10n.co.payroll.simulation.line", "simulation_id", copy=False)
    total_current = fields.Monetary(compute="_compute_totals", currency_field="currency_id")
    total_proposed = fields.Monetary(compute="_compute_totals", currency_field="currency_id")
    total_variation = fields.Monetary(compute="_compute_totals", currency_field="currency_id")
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)
    notes = fields.Text()

    @api.depends("line_ids.current_wage", "line_ids.proposed_wage")
    def _compute_totals(self):
        for record in self:
            record.total_current = sum(record.line_ids.mapped("current_wage"))
            record.total_proposed = sum(record.line_ids.mapped("proposed_wage"))
            record.total_variation = record.total_proposed - record.total_current

    def action_calculate(self):
        for simulation in self:
            simulation.line_ids.sudo().unlink()
            employees = simulation.employee_ids or self.env["hr.employee"].search([("company_id", "=", simulation.company_id.id), ("active", "=", True)])
            values = []
            for employee in employees:
                contract = self.env["hr.version"].search([("employee_id", "=", employee.id), ("company_id", "=", simulation.company_id.id)], order="date_version desc, id desc", limit=1)
                current = contract.wage if contract and "wage" in contract._fields else 0.0
                proposed = current * (1 + simulation.salary_variation / 100.0) + simulation.fixed_variation
                values.append({"simulation_id": simulation.id, "employee_id": employee.id, "contract_id": contract.id if contract else False, "current_wage": current, "proposed_wage": proposed, "employer_cost": proposed * (1 + simulation.employer_rate / 100.0)})
            self.env["l10n.co.payroll.simulation.line"].sudo().create(values)
            simulation.state = "calculated"
        return True

    def action_apply(self):
        for simulation in self:
            if simulation.state != "calculated":
                raise UserError(_("Calcula la simulación antes de aplicarla."))
            for line in simulation.line_ids.filtered(lambda item: item.proposed_wage > 0 and item.current_wage != item.proposed_wage):
                history = self.env["l10n.co.payroll.salary.history"].create({"company_id": simulation.company_id.id, "employee_id": line.employee_id.id, "contract_id": line.contract_id.id, "previous_wage": line.current_wage, "new_wage": line.proposed_wage, "reason": "increase", "effective_date": simulation.date, "notes": simulation.name})
                history.action_approve()
            simulation.state = "applied"


class CoPayrollSimulationLine(models.Model):
    _name = "l10n.co.payroll.simulation.line"
    _description = "Resultado de simulación"
    _order = "employee_id"
    _check_company_auto = True

    simulation_id = fields.Many2one("l10n.co.payroll.simulation", required=True, ondelete="cascade")
    company_id = fields.Many2one(related="simulation_id.company_id", store=True, readonly=True)
    employee_id = fields.Many2one("hr.employee", required=True, readonly=True)
    contract_id = fields.Many2one("hr.version", readonly=True)
    current_wage = fields.Monetary(readonly=True, currency_field="currency_id")
    proposed_wage = fields.Monetary(readonly=True, currency_field="currency_id")
    variation = fields.Monetary(compute="_compute_variation", currency_field="currency_id")
    employer_cost = fields.Monetary(readonly=True, currency_field="currency_id")
    currency_id = fields.Many2one(related="simulation_id.currency_id", readonly=True)

    @api.depends("current_wage", "proposed_wage")
    def _compute_variation(self):
        for record in self:
            record.variation = record.proposed_wage - record.current_wage


class CoPayrollReconciliation(models.Model):
    _name = "l10n.co.payroll.reconciliation"
    _description = "Conciliación bancaria de nómina"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"
    _check_company_auto = True

    name = fields.Char(required=True, default=lambda self: _("Conciliación bancaria"), copy=False)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    batch_id = fields.Many2one("l10n.co.payroll.payment.batch", required=True, ondelete="restrict")
    date = fields.Date(required=True, default=fields.Date.context_today)
    import_file = fields.Binary(string="Extracto CSV")
    import_filename = fields.Char()
    state = fields.Selection([("draft", "Borrador"), ("imported", "Importado"), ("reconciled", "Conciliado"), ("cancelled", "Cancelado")], default="draft", required=True, tracking=True)
    line_ids = fields.One2many("l10n.co.payroll.reconciliation.line", "reconciliation_id", copy=False)
    total_file = fields.Monetary(compute="_compute_totals", currency_field="currency_id")
    total_batch = fields.Monetary(related="batch_id.total_amount", currency_field="currency_id")
    difference = fields.Monetary(compute="_compute_totals", currency_field="currency_id")
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)
    notes = fields.Text()

    @api.depends("line_ids.amount", "total_batch")
    def _compute_totals(self):
        for record in self:
            record.total_file = sum(record.line_ids.mapped("amount"))
            record.difference = record.total_file - record.total_batch

    def action_import(self):
        for record in self:
            if not record.import_file:
                raise UserError(_("Carga un archivo CSV para importar."))
            record.line_ids.sudo().unlink()
            raw = base64.b64decode(record.import_file).decode("utf-8-sig", errors="replace")
            reader = csv.DictReader(io.StringIO(raw), delimiter=";")
            values = []
            for row in reader:
                identification = (row.get("identificacion") or row.get("identificación") or row.get("documento") or "").strip()
                amount = float((row.get("valor") or row.get("amount") or "0").replace(",", "."))
                employee = self.env["hr.employee"].search([("identification_id", "=", identification), ("company_id", "=", record.company_id.id)], limit=1)
                values.append({"reconciliation_id": record.id, "employee_id": employee.id if employee else False, "identification": identification, "amount": amount, "reference": row.get("referencia") or row.get("reference") or "", "state": "matched" if employee else "unmatched"})
            self.env["l10n.co.payroll.reconciliation.line"].create(values)
            record.state = "imported"
        return True

    def action_reconcile(self):
        for record in self:
            if record.state != "imported":
                raise UserError(_("Importa el extracto antes de conciliar."))
            if record.difference:
                raise UserError(_("El total conciliado no coincide con el lote bancario."))
            if record.line_ids.filtered(lambda line: line.state != "matched"):
                raise UserError(_("Hay líneas bancarias sin empleado asociado."))
            record.state = "reconciled"


class CoPayrollReconciliationLine(models.Model):
    _name = "l10n.co.payroll.reconciliation.line"
    _description = "Línea de conciliación bancaria"
    _order = "state, employee_id"
    _check_company_auto = True

    reconciliation_id = fields.Many2one("l10n.co.payroll.reconciliation", required=True, ondelete="cascade")
    company_id = fields.Many2one(related="reconciliation_id.company_id", store=True, readonly=True)
    employee_id = fields.Many2one("hr.employee", readonly=True)
    identification = fields.Char(required=True)
    amount = fields.Monetary(required=True, currency_field="currency_id")
    reference = fields.Char()
    state = fields.Selection([("matched", "Relacionado"), ("unmatched", "Sin relacionar"), ("difference", "Diferencia")], default="unmatched", required=True)
    currency_id = fields.Many2one(related="reconciliation_id.currency_id", readonly=True)


class CoPayrollPeriodEnterprise(models.Model):
    _inherit = "l10n.co.payroll.period"

    calendar_id = fields.Many2one("l10n.co.payroll.calendar", string="Calendario")
    task_ids = fields.One2many("l10n.co.payroll.task", "period_id", string="Tareas", copy=False)
    task_count = fields.Integer(compute="_compute_task_count")
    open_task_count = fields.Integer(compute="_compute_task_count")
    configured_rule_count = fields.Integer(compute="_compute_task_count")
    sandbox_task_count = fields.Integer(compute="_compute_task_count")
    require_checklist = fields.Boolean(string="Exigir checklist de cierre", default=False)
    checklist_ids = fields.One2many("l10n.co.payroll.checklist", "period_id", string="Checklist", copy=False)
    checklist_progress = fields.Float(compute="_compute_checklist")
    snapshot_ids = fields.One2many("l10n.co.payroll.snapshot", "period_id", string="Copias funcionales", copy=False)
    additional_deduction_total = fields.Monetary(string="Descuentos adicionales", compute="_compute_enterprise_totals", currency_field="currency_id")
    payable_net_total = fields.Monetary(string="Neto real a pagar", compute="_compute_enterprise_totals", currency_field="currency_id")
    absence_days_total = fields.Float(string="Días de ausencia", compute="_compute_enterprise_totals")

    @api.depends("line_ids.loan_deduction", "line_ids.embargo_deduction", "line_ids.net_after_deductions", "line_ids.absence_days")
    def _compute_enterprise_totals(self):
        for period in self:
            period.additional_deduction_total = sum(period.line_ids.mapped("additional_deduction_total"))
            period.payable_net_total = sum(period.line_ids.mapped("net_after_deductions"))
            period.absence_days_total = sum(period.line_ids.mapped("absence_days"))

    @api.depends("checklist_ids.state", "checklist_ids.required")
    def _compute_checklist(self):
        for period in self:
            required = period.checklist_ids.filtered("required")
            period.checklist_progress = (len(required.filtered(lambda item: item.state in ("done", "skipped"))) / len(required) * 100.0) if required else 0.0

    @api.depends("task_ids.state", "company_id")
    def _compute_task_count(self):
        for period in self:
            period.task_count = len(period.task_ids)
            period.open_task_count = len(period.task_ids.filtered(lambda task: task.state in ("open", "in_progress")))
            period.configured_rule_count = self.env["l10n.co.payroll.validation.rule"].search_count([("company_id", "=", period.company_id.id), ("active", "=", True)])
            period.sandbox_task_count = len(period.task_ids.filtered(lambda task: task.state in ("open", "in_progress"))) if period.is_sandbox else 0

    def action_prepare(self):
        result = super().action_prepare()
        self._apply_payroll_controls()
        self.action_generate_tasks()
        return result

    def _apply_payroll_controls(self):
        Loan = self.env["l10n.co.payroll.loan"]
        Embargo = self.env["l10n.co.payroll.embargo"]
        Leave = self.env["hr.leave"] if "hr.leave" in self.env.registry.models else False
        for period in self:
            employees = period.line_ids.mapped("employee_id")
            loans = Loan.search([("company_id", "=", period.company_id.id), ("employee_id", "in", employees.ids), ("state", "=", "active"), ("date", "<=", period.date_to)])
            embargoes = Embargo.search([("company_id", "=", period.company_id.id), ("employee_id", "in", employees.ids), ("state", "=", "active"), ("date", "<=", period.date_to)], order="priority, date, id")
            leaves = Leave.search([("company_id", "=", period.company_id.id), ("employee_id", "in", employees.ids), ("state", "=", "validate"), ("date_from", "<=", fields.Datetime.to_datetime(period.date_to).replace(hour=23, minute=59, second=59)), ("date_to", ">=", fields.Datetime.to_datetime(period.date_from))]) if Leave else self.env["hr.employee"].browse()
            for line in period.line_ids:
                line_loans = loans.filtered(lambda loan: loan.employee_id == line.employee_id)
                loan_amount = sum(min(loan.balance, loan.installment) for loan in line_loans)
                line_embargoes = embargoes.filtered(lambda embargo: embargo.employee_id == line.employee_id)
                available = max(line.net_wage - loan_amount, 0.0)
                embargo_amount = 0.0
                for embargo in line_embargoes:
                    requested = embargo.amount if embargo.mode == "fixed" else available * embargo.amount / 100.0
                    current = min(max(embargo.balance, 0.0), requested, available - embargo_amount)
                    embargo_amount += current
                line_leaves = leaves.filtered(lambda leave: leave.employee_id == line.employee_id)
                absence_days = 0.0
                for leave in line_leaves:
                    start = max(fields.Datetime.to_datetime(leave.date_from).date(), period.date_from)
                    end = min(fields.Datetime.to_datetime(leave.date_to).date(), period.date_to)
                    absence_days += max((end - start).days + 1, 0)
                line.sudo().write({"loan_deduction": loan_amount, "embargo_deduction": embargo_amount, "absence_days": absence_days, "net_after_deductions": max(line.net_wage - loan_amount - embargo_amount, 0.0)})

    def action_create_sandbox(self):
        self.ensure_one()
        values = {
            "name": _("Sandbox - %s") % self.name,
            "company_id": self.company_id.id,
            "period_type": self.period_type,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "payment_date": self.payment_date,
            "employee_ids": [(6, 0, self.employee_ids.ids)],
            "department_ids": [(6, 0, self.department_ids.ids)],
            "job_ids": [(6, 0, self.job_ids.ids)],
            "structure_ids": [(6, 0, self.structure_ids.ids)],
            "payslip_run_ids": [(6, 0, self.payslip_run_ids.ids)],
            "parameter_id": self.parameter_id.id,
            "is_sandbox": True,
            "sandbox_source_id": self.id,
            "sandbox_reason": _("Creado desde %s para probar escenarios.") % self.name,
        }
        sandbox = self.create(values)
        return {"type": "ir.actions.act_window", "name": _("Periodo sandbox"), "res_model": self._name, "view_mode": "form", "res_id": sandbox.id, "target": "current"}

    def action_generate_checklist(self):
        Checklist = self.env["l10n.co.payroll.checklist"]
        defaults = [(10, _("Recibos validados y contratos revisados")), (20, _("Validaciones y variaciones revisadas")), (30, _("Novedades aprobadas")), (40, _("PILA revisada")), (50, _("Contabilidad y pagos preparados"))]
        for period in self:
            if not period.checklist_ids:
                Checklist.create([{"name": name, "sequence": sequence, "company_id": period.company_id.id, "period_id": period.id} for sequence, name in defaults])
        return True

    def action_create_snapshot(self):
        self.ensure_one()
        if self.state == "draft":
            raise UserError(_("Prepara el periodo antes de crear una copia funcional."))
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["empleado", "identificacion", "devengado", "deducciones", "prestamos", "embargos", "neto_real", "ausencias"])
        for line in self.line_ids:
            writer.writerow([line.employee_id.name, line.employee_id.identification_id or "", line.gross_wage, line.deduction_total, line.loan_deduction, line.embargo_deduction, line.net_after_deductions, line.absence_days])
        data = output.getvalue().encode("utf-8-sig")
        attachment = self.env["ir.attachment"].create({"name": "%s_SNAPSHOT.csv" % self.name, "type": "binary", "datas": base64.b64encode(data), "res_model": self._name, "res_id": self.id, "mimetype": "text/csv"})
        snapshot = self.env["l10n.co.payroll.snapshot"].create({"name": _("Copia %s") % self.name, "company_id": self.company_id.id, "period_id": self.id, "attachment_id": attachment.id, "checksum": hashlib.sha256(data).hexdigest(), "record_count": len(self.line_ids)})
        self.env["l10n.co.payroll.audit"].sudo().create({"company_id": self.company_id.id, "period_id": self.id, "res_model": snapshot._name, "res_id": snapshot.id, "action": "other", "description": _("Copia funcional del periodo creada.")})
        return snapshot.action_download()

    def action_close(self):
        for period in self:
            if period.require_checklist:
                period.action_generate_checklist()
                pending = period.checklist_ids.filtered(lambda item: item.required and item.state == "pending")
                if pending:
                    raise UserError(_("Completa el checklist de cierre antes de cerrar el periodo."))
        if any(period.is_sandbox for period in self):
            raise UserError(_("Un periodo sandbox no puede cerrarse como nómina real."))
        return super().action_close()

    def action_generate_tasks(self):
        Task = self.env["l10n.co.payroll.task"]
        Rule = self.env["l10n.co.payroll.validation.rule"]
        for period in self:
            period.task_ids.filtered(lambda task: task.state in ("open", "in_progress")).sudo().unlink()
            rules = Rule.search([("company_id", "=", period.company_id.id), ("active", "=", True)], order="sequence, id")
            values = []
            for issue in period.issue_ids.filtered(lambda item: not item.resolved):
                values.append({"name": issue.message, "company_id": period.company_id.id, "period_id": period.id, "employee_id": issue.employee_id.id, "issue_id": issue.id, "task_type": "validation", "priority": "2" if issue.severity == "error" else "1", "description": issue.message, "deadline": period.payment_date})
            employees = period.line_ids.mapped("employee_id")
            for rule in rules:
                for employee in employees:
                    line = period.line_ids.filtered(lambda item: item.employee_id == employee)[:1]
                    missing = False
                    message = False
                    if rule.code == "identification" and not employee.identification_id:
                        missing, message = True, _("Falta identificación para %s.") % employee.name
                    elif rule.code == "social_profile" and not line.social_profile_id:
                        missing, message = True, _("Falta perfil PILA para %s.") % employee.name
                    elif rule.code == "bank_account" and not employee.bank_account_ids:
                        missing, message = True, _("Falta cuenta bancaria para %s.") % employee.name
                    elif rule.code == "minimum_net" and line.net_wage < rule.threshold:
                        missing, message = True, _("El neto de %s está por debajo del mínimo configurado.") % employee.name
                    elif rule.code == "deduction_ratio" and line.gross_wage and line.deduction_total / line.gross_wage * 100 > rule.threshold:
                        missing, message = True, _("Las deducciones de %s superan el porcentaje permitido.") % employee.name
                    if missing:
                        values.append({"name": rule.name, "company_id": period.company_id.id, "period_id": period.id, "employee_id": employee.id, "task_type": "validation", "priority": "2" if rule.severity == "error" else "1", "description": message, "deadline": period.payment_date})
            for line in period.line_ids:
                if line.additional_deduction_total > line.net_wage and line.net_wage > 0:
                    values.append({"name": _("Descuentos superan el neto"), "company_id": period.company_id.id, "period_id": period.id, "employee_id": line.employee_id.id, "task_type": "validation", "priority": "2", "description": _("Préstamos y embargos superan el neto disponible de %s.") % line.employee_id.name, "deadline": period.payment_date})
                parameter = period.parameter_id
                if parameter and parameter.legal_validation_required and parameter.minimum_ibc and line.ibc_base < parameter.minimum_ibc:
                    values.append({"name": _("IBC por debajo del mínimo"), "company_id": period.company_id.id, "period_id": period.id, "employee_id": line.employee_id.id, "task_type": "validation", "priority": "2", "description": _("El IBC de %s está por debajo del mínimo legal parametrizado.") % line.employee_id.name, "deadline": period.payment_date})
                if parameter and parameter.legal_validation_required and parameter.deduction_limit_ratio and line.gross_wage and line.deduction_total / line.gross_wage * 100 > parameter.deduction_limit_ratio:
                    values.append({"name": _("Deducciones sobre el límite"), "company_id": period.company_id.id, "period_id": period.id, "employee_id": line.employee_id.id, "task_type": "validation", "priority": "1", "description": _("Las deducciones de %s superan el límite legal parametrizado.") % line.employee_id.name, "deadline": period.payment_date})
            if values:
                tasks = Task.sudo().create(values)
                for task in tasks.filtered(lambda item: item.assigned_user_id):
                    task.activity_schedule("mail.mail_activity_data_todo", user_id=task.assigned_user_id.id, summary=task.name, note=task.description or task.name)
        return True

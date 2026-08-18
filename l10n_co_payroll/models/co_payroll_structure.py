from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class CoPayrollCostCenter(models.Model):
    _name = "l10n.co.payroll.cost.center"
    _description = "Centro de costo de nómina"
    _order = "name"
    _check_company_auto = True

    name = fields.Char(string="Nombre", required=True)
    code = fields.Char(string="Código", required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    analytic_account_id = fields.Many2one(
        "account.analytic.account",
        string="Cuenta analítica",
        domain="[('company_id', '=', company_id)]",
    )
    default_for_company = fields.Boolean(string="Centro predeterminado", default=False)
    active = fields.Boolean(default=True)
    notes = fields.Text(string="Observaciones")

    _code_unique = models.Constraint(
        "unique(company_id, code)",
        "El código del centro de costo debe ser único por compañía.",
    )

    @api.constrains("default_for_company", "company_id")
    def _check_default(self):
        for record in self.filtered("default_for_company"):
            self.search([
                ("id", "!=", record.id),
                ("company_id", "=", record.company_id.id),
                ("default_for_company", "=", True),
            ]).write({"default_for_company": False})

    @api.model
    def get_for_employee(self, employee):
        """Resolve the simple cost-center priority used by payroll."""
        if getattr(employee, "co_payroll_cost_center_id", False):
            return employee.co_payroll_cost_center_id
        if employee.department_id and getattr(employee.department_id, "co_payroll_cost_center_id", False):
            return employee.department_id.co_payroll_cost_center_id
        return self.search([
            ("company_id", "=", employee.company_id.id),
            ("default_for_company", "=", True),
            ("active", "=", True),
        ], limit=1)


class HrDepartmentCoPayroll(models.Model):
    _inherit = "hr.department"

    co_payroll_cost_center_id = fields.Many2one(
        "l10n.co.payroll.cost.center",
        string="Centro de costo de nómina",
        domain="[('company_id', '=', company_id), ('active', '=', True)]",
    )


class HrEmployeeCoPayroll(models.Model):
    _inherit = "hr.employee"

    co_payroll_cost_center_id = fields.Many2one(
        "l10n.co.payroll.cost.center",
        string="Centro de costo de nómina",
        domain="[('company_id', '=', company_id), ('active', '=', True)]",
    )


class CoPayrollAdministratorAssignment(models.Model):
    _name = "l10n.co.payroll.administrator.assignment"
    _description = "Asignación contable de administradora"
    _order = "priority, id"
    _check_company_auto = True

    name = fields.Char(string="Referencia", required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    administrator_id = fields.Many2one(
        "l10n.co.payroll.administrator",
        string="Administradora",
        required=True,
        domain="[('company_id', '=', company_id), ('active', '=', True)]",
    )
    scope_type = fields.Selection([
        ("employee", "Empleado"),
        ("department", "Departamento"),
        ("company", "Compañía"),
    ], string="Nivel", required=True, default="company")
    employee_id = fields.Many2one("hr.employee", string="Empleado", domain="[('company_id', '=', company_id)]")
    department_id = fields.Many2one("hr.department", string="Departamento", domain="[('company_id', '=', company_id)]")
    priority = fields.Integer(string="Prioridad", default=10, help="Menor número significa mayor prioridad.")
    debit_account_id = fields.Many2one("account.account", string="Cuenta débito alternativa", domain="[('company_ids', 'in', [company_id])]" )
    credit_account_id = fields.Many2one("account.account", string="Cuenta crédito alternativa", domain="[('company_ids', 'in', [company_id])]" )
    partner_id = fields.Many2one("res.partner", string="Tercero alternativo")
    analytic_account_id = fields.Many2one("account.analytic.account", string="Cuenta analítica", domain="[('company_id', '=', company_id)]")
    active = fields.Boolean(default=True)
    notes = fields.Text(string="Observaciones")

    @api.constrains("scope_type", "employee_id", "department_id", "company_id", "administrator_id")
    def _check_scope(self):
        for record in self:
            if record.scope_type == "employee" and not record.employee_id:
                raise ValidationError(_("Una asignación por empleado debe indicar el empleado."))
            if record.scope_type == "department" and not record.department_id:
                raise ValidationError(_("Una asignación por departamento debe indicar el departamento."))
            if record.scope_type == "company" and (record.employee_id or record.department_id):
                raise ValidationError(_("Una asignación por compañía no debe tener empleado ni departamento."))
            if record.administrator_id.company_id != record.company_id:
                raise ValidationError(_("La administradora y la asignación deben pertenecer a la misma compañía."))

    @api.model
    def get_for(self, company, employee, kind, base_administrator=False):
        """Return the most specific assignment: employee, department, company."""
        candidates = self.search([
            ("company_id", "=", company.id),
            ("administrator_id.kind", "=", kind),
            ("administrator_id.active", "=", True),
            ("active", "=", True),
            "|", ("employee_id", "=", employee.id),
            "|", ("department_id", "=", employee.department_id.id),
            ("scope_type", "=", "company"),
        ])
        ranked = sorted(candidates, key=lambda item: (
            0 if item.scope_type == "employee" else 1 if item.scope_type == "department" else 2,
            0 if base_administrator and item.administrator_id == base_administrator else 1,
            item.priority,
            item.id,
        ))
        return ranked[0] if ranked else self.browse()


class CoPayrollPaymentAllocation(models.Model):
    _name = "l10n.co.payroll.payment.allocation"
    _description = "Distribución bancaria del empleado"
    _order = "employee_id, sequence, id"
    _check_company_auto = True

    name = fields.Char(string="Referencia", required=True, default=lambda self: _("Distribución bancaria"))
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    employee_id = fields.Many2one("hr.employee", required=True, domain="[('company_id', '=', company_id)]", index=True)
    bank_account_id = fields.Many2one("res.partner.bank", string="Cuenta bancaria", required=True)
    percentage = fields.Float(string="Porcentaje", required=True, default=100.0)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    notes = fields.Text(string="Observaciones")

    @api.constrains("percentage", "employee_id", "company_id", "bank_account_id")
    def _check_values(self):
        for record in self:
            if record.percentage <= 0 or record.percentage > 100:
                raise ValidationError(_("El porcentaje debe estar entre 0 y 100."))
            if record.employee_id.company_id != record.company_id:
                raise ValidationError(_("El empleado debe pertenecer a la compañía."))
            if record.bank_account_id not in record.employee_id.bank_account_ids:
                raise ValidationError(_("La cuenta bancaria debe pertenecer al empleado."))

    _employee_bank_unique = models.Constraint(
        "unique(employee_id, bank_account_id)",
        "Una cuenta bancaria solo puede aparecer una vez por empleado.",
    )

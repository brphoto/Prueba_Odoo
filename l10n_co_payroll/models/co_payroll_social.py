from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class CoPayrollSocialProfile(models.Model):
    _name = "l10n.co.payroll.social"
    _description = "Perfil de seguridad social PILA"
    _order = "effective_from desc, id desc"
    _check_company_auto = True

    name = fields.Char(string="Referencia", required=True, copy=False, default=lambda self: _("Perfil PILA"))
    employee_id = fields.Many2one("hr.employee", required=True, index=True)
    company_id = fields.Many2one(related="employee_id.company_id", store=True, readonly=True, index=True)
    effective_from = fields.Date(string="Vigente desde", required=True, default=fields.Date.context_today, index=True)
    effective_to = fields.Date(string="Vigente hasta", index=True)
    state = fields.Selection([("draft", "Borrador"), ("active", "Activo"), ("archived", "Archivado")], default="draft", required=True)
    salary_mode = fields.Selection([
        ("ordinary", "Salario ordinario"),
        ("integral", "Salario integral"),
    ], string="Modalidad salarial", required=True, default="ordinary", help="Se usa para determinar el IBC legal del periodo.")
    contributor_type = fields.Char(string="Tipo cotizante", required=True, default="01")
    contributor_subtype = fields.Char(string="Subtipo", required=True, default="0")
    identification_type = fields.Char(string="Tipo documento", default="CC")
    eps_code = fields.Char(string="Código EPS")
    pension_code = fields.Char(string="Código AFP")
    arl_code = fields.Char(string="Código ARL")
    ccf_code = fields.Char(string="Código caja")
    risk_class = fields.Selection([("I", "I"), ("II", "II"), ("III", "III"), ("IV", "IV"), ("V", "V")], string="Clase de riesgo", default="I")
    notes = fields.Text(string="Observaciones")

    @api.constrains("effective_from", "effective_to")
    def _check_dates(self):
        for record in self:
            if record.effective_to and record.effective_from > record.effective_to:
                raise ValidationError(_("La fecha inicial del perfil PILA no puede superar la fecha final."))
            overlap = self.search([
                ("id", "!=", record.id),
                ("employee_id", "=", record.employee_id.id),
                ("state", "!=", "archived"),
                ("effective_from", "<=", record.effective_to or "2200-12-31"),
                ("effective_to", "=", False),
            ], limit=1)
            if overlap and not record.effective_to:
                raise ValidationError(_("El empleado ya tiene un perfil PILA abierto."))

    def action_activate(self):
        for record in self:
            self.search([("employee_id", "=", record.employee_id.id), ("id", "!=", record.id), ("state", "=", "active")]).write({"state": "archived", "effective_to": record.effective_from - relativedelta(days=1)})
            record.write({"state": "active"})
        return True

    def action_archive(self):
        self.write({"state": "archived"})
        return True

    @api.model
    def get_for_employee(self, employee, date):
        return self.search([
            ("employee_id", "=", employee.id),
            ("state", "=", "active"),
            ("effective_from", "<=", date),
            "|", ("effective_to", "=", False), ("effective_to", ">=", date),
        ], order="effective_from desc, id desc", limit=1)

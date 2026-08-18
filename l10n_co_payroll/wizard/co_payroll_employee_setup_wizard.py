from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CoPayrollEmployeeSetupWizard(models.TransientModel):
    _name = "l10n.co.payroll.employee.setup.wizard"
    _description = "Vinculación sencilla de empleado a PILA"

    employee_id = fields.Many2one("hr.employee", string="Empleado", required=True, domain="[('company_id', '=', company_id)]")
    company_id = fields.Many2one(related="employee_id.company_id", string="Compañía", readonly=True)
    effective_from = fields.Date(string="Vigente desde", required=True, default=fields.Date.context_today)
    salary_mode = fields.Selection([
        ("ordinary", "Salario ordinario"), ("integral", "Salario integral"),
    ], string="Modalidad salarial", required=True, default="ordinary")
    contributor_type = fields.Selection([
        ("01", "01 - Dependiente"), ("02", "02 - Servicio doméstico"), ("03", "03 - Independiente"),
        ("04", "04 - Agremiado"), ("12", "12 - Aprendiz etapa lectiva"), ("19", "19 - Aprendiz productiva"),
        ("23", "23 - Estudiante aporte"), ("40", "40 - Beneficiario UPC"), ("51", "51 - Independiente agremiado"),
        ("52", "52 - Independiente cuenta propia"),
    ], string="Tipo cotizante", required=True, default="01")
    contributor_subtype = fields.Selection([
        ("0", "0 - No aplica"), ("1", "1 - Dependiente"), ("2", "2 - Servicio doméstico"),
        ("3", "3 - Independiente"), ("4", "4 - Madre comunitaria"),
    ], string="Subtipo", required=True, default="0")
    coverage_mode = fields.Selection([
        ("full", "Afiliación completa"), ("manual", "Reporte externo / manual"), ("not_applicable", "No aplica PILA"),
    ], string="Cobertura PILA", required=True, default="full")
    manual_reference = fields.Char(string="Referencia externa / motivo")
    eps_id = fields.Many2one("l10n.co.payroll.administrator", string="EPS / Salud", domain="[('company_id', '=', company_id), ('kind', '=', 'eps'), ('active', '=', True)]")
    pension_id = fields.Many2one("l10n.co.payroll.administrator", string="AFP / Pensión", domain="[('company_id', '=', company_id), ('kind', '=', 'pension'), ('active', '=', True)]")
    arl_id = fields.Many2one("l10n.co.payroll.administrator", string="ARL", domain="[('company_id', '=', company_id), ('kind', '=', 'arl'), ('active', '=', True)]")
    ccf_id = fields.Many2one("l10n.co.payroll.administrator", string="Caja de compensación", domain="[('company_id', '=', company_id), ('kind', '=', 'ccf'), ('active', '=', True)]")
    risk_class = fields.Selection([("I", "I"), ("II", "II"), ("III", "III"), ("IV", "IV"), ("V", "V")], string="Clase de riesgo", default="I")
    require_eps = fields.Boolean(string="Exigir EPS", default=True)
    require_pension = fields.Boolean(string="Exigir pensión", default=True)
    require_arl = fields.Boolean(string="Exigir ARL", default=True)
    require_ccf = fields.Boolean(string="Exigir caja", default=True)
    cost_center_id = fields.Many2one("l10n.co.payroll.cost.center", string="Centro de costo", domain="[('company_id', '=', company_id), ('active', '=', True)]")
    replace_active = fields.Boolean(string="Reemplazar perfil activo", default=True, help="Archiva el perfil anterior desde la fecha de inicio del nuevo perfil.")

    @api.onchange("coverage_mode")
    def _onchange_coverage_mode(self):
        if self.coverage_mode != "full":
            self.require_eps = self.require_pension = self.require_arl = self.require_ccf = False

    def action_apply(self):
        self.ensure_one()
        if self.coverage_mode == "full":
            missing = []
            for required, administrator, label in (
                (self.require_eps, self.eps_id, _("EPS / Salud")),
                (self.require_pension, self.pension_id, _("AFP / Pensión")),
                (self.require_arl, self.arl_id, _("ARL")),
                (self.require_ccf, self.ccf_id, _("Caja de compensación")),
            ):
                if required and not administrator:
                    missing.append(label)
            if missing:
                raise UserError(_("Completa las administradoras obligatorias: %s.") % ", ".join(missing))
        elif not self.manual_reference:
            raise UserError(_("Indica la referencia externa o el motivo de no aplicación."))

        Social = self.env["l10n.co.payroll.social"].sudo()
        if self.replace_active:
            Social.search([
                ("employee_id", "=", self.employee_id.id), ("state", "=", "active"),
                ("id", "!=", False),
            ]).write({"state": "archived", "effective_to": self.effective_from - relativedelta(days=1)})
        profile = Social.create({
            "name": _("Perfil PILA - %s") % self.employee_id.name,
            "employee_id": self.employee_id.id,
            "effective_from": self.effective_from,
            "state": "active",
            "coverage_mode": self.coverage_mode,
            "manual_reference": self.manual_reference,
            "salary_mode": self.salary_mode,
            "contributor_type": self.contributor_type,
            "contributor_subtype": self.contributor_subtype,
            "eps_id": self.eps_id.id,
            "pension_id": self.pension_id.id,
            "arl_id": self.arl_id.id,
            "ccf_id": self.ccf_id.id,
            "risk_class": self.risk_class,
            "require_eps": self.require_eps,
            "require_pension": self.require_pension,
            "require_arl": self.require_arl,
            "require_ccf": self.require_ccf,
        })
        if self.cost_center_id:
            self.employee_id.sudo().write({"co_payroll_cost_center_id": self.cost_center_id.id})
        return {
            "type": "ir.actions.act_window",
            "name": _("Perfil PILA creado"),
            "res_model": "l10n.co.payroll.social",
            "view_mode": "form",
            "res_id": profile.id,
        }

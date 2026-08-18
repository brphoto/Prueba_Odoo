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
    coverage_mode = fields.Selection([
        ("full", "Afiliación completa"),
        ("manual", "Reporte externo / manual"),
        ("not_applicable", "No aplica PILA"),
    ], string="Modo de cobertura", required=True, default="full", help="Define si el empleado se reporta con administradoras, lo maneja un operador externo o no debe reportarse.")
    manual_reference = fields.Char(string="Referencia externa / motivo", help="Obligatoria para reporte manual o no aplica.")
    require_eps = fields.Boolean(string="Exigir EPS", default=True)
    require_pension = fields.Boolean(string="Exigir pensión", default=True)
    require_arl = fields.Boolean(string="Exigir ARL", default=True)
    require_ccf = fields.Boolean(string="Exigir caja", default=True)
    salary_mode = fields.Selection([
        ("ordinary", "Salario ordinario"),
        ("integral", "Salario integral"),
    ], string="Modalidad salarial", required=True, default="ordinary", help="Se usa para determinar el IBC legal del periodo.")
    contributor_type = fields.Selection([
        ("01", "01 - Dependiente"), ("02", "02 - Servicio doméstico"),
        ("03", "03 - Independiente"), ("04", "04 - Agremiado"),
        ("12", "12 - Aprendiz etapa lectiva"), ("19", "19 - Aprendiz productiva"),
        ("23", "23 - Estudiante aporte"), ("40", "40 - Beneficiario UPC"),
        ("51", "51 - Independiente agremiado"), ("52", "52 - Independiente cuenta propia"),
    ], string="Tipo cotizante", required=True, default="01")
    contributor_subtype = fields.Selection([
        ("0", "0 - No aplica"), ("1", "1 - Dependiente"), ("2", "2 - Servicio doméstico"),
        ("3", "3 - Independiente"), ("4", "4 - Madre comunitaria"),
    ], string="Subtipo", required=True, default="0")
    identification_type = fields.Selection([
        ("CC", "Cédula de ciudadanía"), ("CE", "Cédula de extranjería"),
        ("TI", "Tarjeta de identidad"), ("PA", "Pasaporte"), ("PEP", "Permiso especial"),
    ], string="Tipo documento", default="CC")
    eps_id = fields.Many2one(
        "l10n.co.payroll.administrator", string="EPS / Salud",
        domain="[('kind', '=', 'eps'), ('active', '=', True), ('company_id', '=', company_id)]",
    )
    pension_id = fields.Many2one(
        "l10n.co.payroll.administrator", string="AFP / Pensión",
        domain="[('kind', '=', 'pension'), ('active', '=', True), ('company_id', '=', company_id)]",
    )
    arl_id = fields.Many2one(
        "l10n.co.payroll.administrator", string="ARL",
        domain="[('kind', '=', 'arl'), ('active', '=', True), ('company_id', '=', company_id)]",
    )
    ccf_id = fields.Many2one(
        "l10n.co.payroll.administrator", string="Caja de compensación",
        domain="[('kind', '=', 'ccf'), ('active', '=', True), ('company_id', '=', company_id)]",
    )
    eps_code = fields.Char(string="Código EPS")
    pension_code = fields.Char(string="Código AFP")
    arl_code = fields.Char(string="Código ARL")
    ccf_code = fields.Char(string="Código caja")
    risk_class = fields.Selection([("I", "I"), ("II", "II"), ("III", "III"), ("IV", "IV"), ("V", "V")], string="Clase de riesgo", default="I")
    notes = fields.Text(string="Observaciones")

    def get_missing_administrators(self):
        self.ensure_one()
        if self.coverage_mode != "full":
            return []
        required = (
            (self.require_eps, self.eps_id or self.eps_code, _("EPS / Salud")),
            (self.require_pension, self.pension_id or self.pension_code, _("AFP / Pensión")),
            (self.require_arl, self.arl_id or self.arl_code, _("ARL")),
            (self.require_ccf, self.ccf_id or self.ccf_code, _("Caja de compensación")),
        )
        return [label for required_flag, administrator, label in required if required_flag and not administrator]

    @property
    def is_pila_reportable(self):
        return self.coverage_mode == "full"

    @api.onchange("eps_id", "pension_id", "arl_id", "ccf_id")
    def _onchange_administrators(self):
        for record in self:
            record._sync_administrator_codes()

    def _sync_administrator_codes(self):
        for record in self:
            if record.eps_id:
                record.eps_code = record.eps_id.code
            if record.pension_id:
                record.pension_code = record.pension_id.code
            if record.arl_id:
                record.arl_code = record.arl_id.code
            if record.ccf_id:
                record.ccf_code = record.ccf_id.code

    @api.model_create_multi
    def create(self, vals_list):
        Administrator = self.env["l10n.co.payroll.administrator"]
        for vals in vals_list:
            for administrator_field, code_field in (
                ("eps_id", "eps_code"),
                ("pension_id", "pension_code"),
                ("arl_id", "arl_code"),
                ("ccf_id", "ccf_code"),
            ):
                administrator = Administrator.browse(vals.get(administrator_field)).exists()
                if administrator:
                    vals[code_field] = administrator.code
        return super().create(vals_list)

    def write(self, vals):
        vals = dict(vals)
        Administrator = self.env["l10n.co.payroll.administrator"]
        for administrator_field, code_field in (
            ("eps_id", "eps_code"),
            ("pension_id", "pension_code"),
            ("arl_id", "arl_code"),
            ("ccf_id", "ccf_code"),
        ):
            administrator = Administrator.browse(vals.get(administrator_field)).exists()
            if administrator:
                vals[code_field] = administrator.code
        return super().write(vals)

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

    @api.constrains("coverage_mode", "manual_reference", "state")
    def _check_coverage(self):
        for record in self:
            if record.state == "active" and record.coverage_mode == "full" and record.get_missing_administrators():
                raise ValidationError(_("Completa las administradoras obligatorias: %s.") % ", ".join(record.get_missing_administrators()))
            if record.state == "active" and record.coverage_mode in ("manual", "not_applicable") and not record.manual_reference:
                raise ValidationError(_("Indica una referencia o motivo para el modo de cobertura seleccionado."))

    def action_activate(self):
        for record in self:
            missing = record.get_missing_administrators()
            if record.coverage_mode == "full" and missing:
                raise ValidationError(_("Completa las administradoras obligatorias: %s.") % ", ".join(missing))
            if record.coverage_mode in ("manual", "not_applicable") and not record.manual_reference:
                raise ValidationError(_("Indica una referencia o motivo antes de activar el perfil."))
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

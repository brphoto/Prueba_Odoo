from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class CoPayrollRuleMapping(models.Model):
    _name = "l10n.co.payroll.rule.mapping"
    _description = "Mapeo legal de conceptos de nómina"
    _order = "priority, code"
    _check_company_auto = True

    @api.model
    def _default_parameter_id(self):
        return self.env["l10n.co.payroll.parameter"].search([
            ("company_id", "=", self.env.company.id),
            ("status", "=", "active"),
        ], order="effective_from desc, version desc, id desc", limit=1)

    name = fields.Char(string="Nombre", required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    parameter_id = fields.Many2one(
        "l10n.co.payroll.parameter", string="Versión legal", required=True,
        default=_default_parameter_id, ondelete="cascade",
        domain="[('company_id', '=', company_id)]",
    )
    salary_rule_id = fields.Many2one(
        "l10n.co.payroll.salary.rule",
        string="Regla salarial vinculada",
        ondelete="cascade",
        index=True,
        domain="[('company_id', '=', company_id), ('parameter_id', '=', parameter_id)]",
        help="Regla jurídica estable a la que pertenece este concepto.",
    )
    native_rule_id = fields.Many2one(
        "hr.salary.rule",
        string="Regla nativa de Odoo",
        ondelete="set null",
        index=True,
        help="Referencia técnica opcional para reglas nativas personalizadas.",
    )
    code = fields.Char(string="Código regla", required=True, help="Código técnico interno de la regla salarial.")
    concept_type = fields.Selection([
        ("earning", "Devengado"),
        ("deduction", "Deducción"),
        ("employee_contribution", "Aporte del colaborador"),
        ("employer", "Aporte empresa"),
        ("employer_contribution", "Aporte del empleador"),
        ("ibc", "IBC"),
        ("social_base", "Base de seguridad social"),
        ("provision", "Provisión"),
    ], string="Tipo", required=True)
    pila_code = fields.Char(string="Código PILA")
    include_in_ibc = fields.Boolean(string="Incluye en IBC")
    active = fields.Boolean(default=True)
    is_system_default = fields.Boolean(string="Predeterminado del producto", default=False, readonly=True, copy=False)
    priority = fields.Integer(default=10)
    notes = fields.Text(string="Notas")

    _parameter_code_unique = models.Constraint(
        "unique(parameter_id, code, concept_type)",
        "Ya existe este concepto para la vigencia legal.",
    )

    @api.constrains("parameter_id", "company_id")
    def _check_company_parameter(self):
        for record in self:
            if record.parameter_id.company_id != record.company_id:
                raise ValidationError(_("La versión legal debe pertenecer a la misma compañía."))
            if record.salary_rule_id and (
                record.salary_rule_id.company_id != record.company_id
                or record.salary_rule_id.parameter_id != record.parameter_id
            ):
                raise ValidationError(_("La regla salarial vinculada debe pertenecer a la misma compañía y versión legal."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            rule = self.env["l10n.co.payroll.salary.rule"].browse(vals.get("salary_rule_id")).exists()
            native = self.env["hr.salary.rule"].browse(vals.get("native_rule_id")).exists()
            if rule:
                vals.setdefault("name", rule.name)
                vals.setdefault("code", rule.code)
            elif native:
                vals.setdefault("name", native.name)
                vals.setdefault("code", native.code)
        return super().create(vals_list)

    @api.onchange("salary_rule_id")
    def _onchange_salary_rule_id(self):
        for record in self:
            if record.salary_rule_id:
                record.name = record.name or record.salary_rule_id.name
                record.code = record.salary_rule_id.code
                record.parameter_id = record.salary_rule_id.parameter_id
                record.company_id = record.salary_rule_id.company_id

    @api.onchange("native_rule_id")
    def _onchange_native_rule_id(self):
        for record in self:
            if record.native_rule_id and not record.salary_rule_id:
                record.name = record.name or record.native_rule_id.name
                record.code = record.native_rule_id.code

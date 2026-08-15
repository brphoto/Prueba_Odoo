from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class NavNominaRuleMapping(models.Model):
    _name = "nav.nomina.rule.mapping"
    _description = "Mapeo legal de conceptos de nómina"
    _order = "priority, code"
    _check_company_auto = True

    name = fields.Char(string="Nombre", required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    parameter_id = fields.Many2one("nav.nomina.parameter", string="Versión legal", required=True, ondelete="cascade", domain="[('company_id', '=', company_id)]")
    code = fields.Char(string="Código regla", required=True, help="Código de la regla salarial de Odoo.")
    concept_type = fields.Selection([("earning", "Devengado"), ("deduction", "Deducción"), ("employer", "Aporte empresa"), ("ibc", "IBC"), ("provision", "Provisión")], string="Tipo", required=True)
    pila_code = fields.Char(string="Código PILA")
    include_in_ibc = fields.Boolean(string="Incluye en IBC")
    active = fields.Boolean(default=True)
    priority = fields.Integer(default=10)
    notes = fields.Text(string="Notas")

    _parameter_code_unique = models.Constraint("unique(parameter_id, code, concept_type)", "Ya existe este mapeo para la versión legal.")

    @api.constrains("parameter_id", "company_id")
    def _check_company_parameter(self):
        for record in self:
            if record.parameter_id.company_id != record.company_id:
                raise ValidationError(_("La versión legal debe pertenecer a la misma compañía."))

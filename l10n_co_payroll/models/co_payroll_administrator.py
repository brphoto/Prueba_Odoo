from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class CoPayrollAdministrator(models.Model):
    _name = "l10n.co.payroll.administrator"
    _description = "Administradora PILA"
    _order = "kind, name"
    _check_company_auto = True

    name = fields.Char(string="Nombre", required=True)
    company_id = fields.Many2one(
        "res.company", string="Compañía", required=True,
        default=lambda self: self.env.company, index=True,
    )
    kind = fields.Selection([
        ("eps", "EPS / Salud"),
        ("pension", "AFP / Pensión"),
        ("arl", "ARL"),
        ("ccf", "Caja de compensación"),
    ], string="Tipo", required=True)
    code = fields.Char(string="Código PILA", required=True, help="Código de la administradora usado en PILA.")
    partner_id = fields.Many2one("res.partner", string="Tercero contable")
    debit_account_id = fields.Many2one("account.account", string="Cuenta débito")
    credit_account_id = fields.Many2one("account.account", string="Cuenta crédito")
    active = fields.Boolean(default=True)
    notes = fields.Text(string="Observaciones")

    _code_unique = models.Constraint(
        "unique(company_id, kind, code)",
        "Ya existe una administradora con ese código para este tipo y compañía.",
    )

    @api.constrains("code")
    def _check_code(self):
        for record in self:
            if record.code and record.code.strip() != record.code:
                raise ValidationError(_("El código PILA no debe comenzar ni terminar con espacios."))


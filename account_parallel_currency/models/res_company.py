from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = 'res.company'

    other_currency_id = fields.Many2one(
        comodel_name='res.currency',
        string="Otra Moneda",
        help="Segunda moneda de valoración de los apuntes. Vacío = desactivado.",
        domain="[('id', '!=', currency_id), ('active', '=', True)]",
    )
    other_currency_rounding_tolerance = fields.Monetary(
        string="Tolerancia de redondeo",
        currency_field='other_currency_id',
        default=0.01,
        help="Descuadre máximo en la otra moneda que se compensa automáticamente al publicar.",
    )
    other_currency_loss_account_id = fields.Many2one(
        comodel_name='account.account',
        string="Cuenta de pérdida",
        check_company=True,
        domain="[('internal_group', '=', 'expense')]",
        help="Cuenta de gasto. Se usa cuando falta debe en la otra moneda.",
    )
    other_currency_gain_account_id = fields.Many2one(
        comodel_name='account.account',
        string="Cuenta de ganancia",
        check_company=True,
        domain="[('internal_group', '=', 'income')]",
        help="Cuenta de ingreso. Se usa cuando falta haber en la otra moneda.",
    )


    @api.constrains('other_currency_rounding_tolerance')
    def _check_other_currency_rounding_tolerance(self):
        for company in self:
            if company.other_currency_rounding_tolerance < 0:
                raise ValidationError(_("La tolerancia de redondeo no puede ser negativa."))

    @api.constrains('other_currency_loss_account_id', 'other_currency_gain_account_id')
    def _check_other_currency_rounding_accounts(self):
        for company in self:
            loss = company.other_currency_loss_account_id
            if loss and loss.internal_group != 'expense':
                raise ValidationError(_(
                    "%(account)s no es cuenta de gasto: no puede registrar la pérdida por redondeo.",
                    account=loss.display_name,
                ))
            gain = company.other_currency_gain_account_id
            if gain and gain.internal_group != 'income':
                raise ValidationError(_(
                    "%(account)s no es cuenta de ingreso: no puede registrar la ganancia por redondeo.",
                    account=gain.display_name,
                ))

    def _get_other_currency_rounding_account(self, difference):
        """Devuelve la cuenta a usar , segun el descuadre en la operacion"""
        
        self.ensure_one()
        return self.other_currency_gain_account_id if difference > 0 else self.other_currency_loss_account_id

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    other_currency_id = fields.Many2one(
        related='company_id.other_currency_id',
        string="Otra Moneda",
        readonly=False,
        domain="[('id', '!=', currency_id), ('active', '=', True)]",
    )
    other_currency_rounding_tolerance = fields.Monetary(
        related='company_id.other_currency_rounding_tolerance',
        string="Tolerancia de redondeo",
        currency_field='other_currency_id',
        readonly=False,
    )
    other_currency_loss_account_id = fields.Many2one(
        related='company_id.other_currency_loss_account_id',
        string="Cuenta de pérdida",
        readonly=False,
        check_company=True,
        domain="[('internal_group', '=', 'expense')]",
    )
    other_currency_gain_account_id = fields.Many2one(
        related='company_id.other_currency_gain_account_id',
        string="Cuenta de ganancia",
        readonly=False,
        check_company=True,
        domain="[('internal_group', '=', 'income')]",
    )

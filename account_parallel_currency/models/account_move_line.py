from odoo import api, fields, models

ROUNDING_OTHER_CURRENCY = 'rounding_other_currency'


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    display_type = fields.Selection(
        selection_add=[(ROUNDING_OTHER_CURRENCY, "Ajuste por redondeo")],
        ondelete={ROUNDING_OTHER_CURRENCY: 'cascade'},
    )
    other_currency_id = fields.Many2one(
        related='company_id.other_currency_id',
        string="Otra Moneda",
    )
    debit_other_currency = fields.Monetary(
        string="Debe en Otra Moneda",
        compute='_compute_amounts_other_currency', store=True,
        currency_field='other_currency_id',
    )
    credit_other_currency = fields.Monetary(
        string="Haber en Otra Moneda",
        compute='_compute_amounts_other_currency', store=True,
        currency_field='other_currency_id',
    )
    other_currency_rounding_amount = fields.Monetary(
        string="Ajuste por redondeo",
        currency_field='other_currency_id',
        copy=False,
        help="Descuadre que cierra este apunte. Solo en líneas generadas automáticamente.",
    )

    @api.depends('debit', 'credit', 'date', 'display_type', 'other_currency_rounding_amount',
                 'company_id.other_currency_id')
    def _compute_amounts_other_currency(self):
        """Valora los importes en la otra moneda, según el tipo de cambio de la fecha del apunte."""
        Currency = self.env['res.currency']
        for line in self:
            currency = line.other_currency_id
            if not currency:
                line.debit_other_currency = line.credit_other_currency = 0.0
            elif line.display_type == ROUNDING_OTHER_CURRENCY:
                amount = line.other_currency_rounding_amount
                line.debit_other_currency = -amount if amount < 0 else 0.0
                line.credit_other_currency = amount if amount > 0 else 0.0
            else:
                company = line.company_id
                rate = Currency._get_conversion_rate(
                    company.currency_id, currency, company,
                    line.date or fields.Date.context_today(line),
                )
                line.debit_other_currency = currency.round(line.debit * rate)
                line.credit_other_currency = currency.round(line.credit * rate)

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare, format_amount

from .account_move_line import ROUNDING_OTHER_CURRENCY


class AccountMove(models.Model):
    _inherit = 'account.move'

    other_currency_id = fields.Many2one(
        related='company_id.other_currency_id',
        string="Otra Moneda",
    )
    total_debit_other_currency = fields.Monetary(
        string="Total Debe en Otra Moneda",
        compute='_compute_totals_other_currency',
        currency_field='other_currency_id',
    )
    total_credit_other_currency = fields.Monetary(
        string="Total Haber en Otra Moneda",
        compute='_compute_totals_other_currency',
        currency_field='other_currency_id',
    )

    @api.depends('line_ids.debit_other_currency', 'line_ids.credit_other_currency')
    def _compute_totals_other_currency(self):
        """Totaliza el asiento en la otra moneda, para el pie del formulario."""
        for move in self:
            currency = move.other_currency_id
            move.total_debit_other_currency = (
                currency.round(sum(move.line_ids.mapped('debit_other_currency'))) if currency else 0.0
            )
            move.total_credit_other_currency = (
                currency.round(sum(move.line_ids.mapped('credit_other_currency'))) if currency else 0.0
            )

    def _post(self, soft=True):
        """Aplica el redondeo en la otra moneda antes de validar el asiento."""
        self._apply_other_currency_rounding()
        return super()._post(soft=soft)

    def button_draft(self):
        res = super().button_draft()
        self._get_other_currency_rounding_lines().unlink()
        return res

    def _get_other_currency_rounding_lines(self):
        return self.line_ids.filtered(lambda line: line.display_type == ROUNDING_OTHER_CURRENCY)

    def _get_other_currency_imbalance(self):
        """Devuelve el total del debe menos el total del haber del asiento, en la otra moneda."""
        self.ensure_one()
        currency = self.other_currency_id
        if not currency:
            return 0.0
        lines = self.line_ids
        return currency.round(
            sum(lines.mapped('debit_other_currency')) - sum(lines.mapped('credit_other_currency'))
        )

    def _prepare_other_currency_rounding_line_values(self, difference):
        """Prepara los valores de la línea de redondeo en la otra moneda para cuadrar el asiento."""
        self.ensure_one()
        return {
            'name': _("Ajuste por redondeo"),
            'account_id': self.company_id._get_other_currency_rounding_account(difference).id,
            'display_type': ROUNDING_OTHER_CURRENCY,
            'debit': 0.0,
            'credit': 0.0,
            'other_currency_rounding_amount': difference,
        }

    def _apply_other_currency_rounding(self):
        """Cuadra los asientos en la otra moneda compensando la diferencia por redondeo."""
        
        for move in self:
            company = move.company_id
            currency = company.other_currency_id
            if not currency:
                continue

            move._get_other_currency_rounding_lines().unlink()
            difference = move._get_other_currency_imbalance()
            if currency.is_zero(difference):
                continue

            if float_compare(abs(difference), company.other_currency_rounding_tolerance,
                             precision_rounding=currency.rounding) > 0:
                raise UserError(_(
                    "%(move)s está descuadrado en %(difference)s y supera la tolerancia de %(tolerance)s.",
                    move=move.display_name,
                    difference=format_amount(self.env, abs(difference), currency),
                    tolerance=format_amount(self.env, company.other_currency_rounding_tolerance, currency),
                ))
            if not company._get_other_currency_rounding_account(difference):
                raise UserError(_(
                    "No hay cuenta de %(direction)s por redondeo en %(company)s.",
                    direction=_("ganancia") if difference > 0 else _("pérdida"),
                    company=company.display_name,
                ))

            move.line_ids = [
                Command.create(move._prepare_other_currency_rounding_line_values(difference))
            ]

           
            remaining = move._get_other_currency_imbalance()
            if not currency.is_zero(remaining):
                raise UserError(_(
                    "%(move)s no cuadra en %(currency)s: quedan %(difference)s.",
                    move=move.display_name,
                    currency=currency.display_name,
                    difference=format_amount(self.env, remaining, currency),
                ))

# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class CrmRfmRecomputeWizard(models.TransientModel):
    _name = 'crm.rfm.recompute.wizard'
    _description = 'Recalcular Clasificación RFM'

    last_computed_at = fields.Datetime(
        string='Último cálculo', compute='_compute_last_computed_at', readonly=True)
    date_from = fields.Date(required=True, string='Desde')
    date_to = fields.Date(required=True, string='Hasta', default=fields.Date.context_today)

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        today = fields.Date.context_today(self)
        vals.setdefault('date_to', today)
        vals.setdefault('date_from', today - timedelta(days=365))
        return vals

    def _compute_last_computed_at(self):
        computed_dates = self.env['res.partner'].search(
            [('rfm_last_computed_at', '!=', False)],
        ).mapped('rfm_last_computed_at')
        last = max(computed_dates) if computed_dates else False
        for wizard in self:
            wizard.last_computed_at = last

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from > wizard.date_to:
                raise ValidationError(_('La fecha "Desde" no puede ser posterior a "Hasta".'))

    def action_recompute(self):
        self.ensure_one()
        self.env['res.partner']._cron_compute_rfm_scores(
            date_from=self.date_from, date_to=self.date_to)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Inteligencia comercial'),
                'message': _('Recálculo RFM completado (%(from)s a %(to)s).') % {
                    'from': self.date_from, 'to': self.date_to,
                },
                'type': 'success',
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

# -*- coding: utf-8 -*-
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    engagement_birthday = fields.Date(
        string='Fecha de cumpleaños',
        help='Se usa para recordatorios anuales. El año se ignora y solo se compara mes y día.')
    engagement_note = fields.Char(
        string='Nota para automatizaciones',
        help='Dato breve que puede utilizarse como contexto al personalizar la comunicación.')
    engagement_event_count = fields.Integer(
        string='Eventos programados', compute='_compute_engagement_event_count')

    def _compute_engagement_event_count(self):
        Event = self.env['crm.engagement.event']
        for partner in self:
            partner.engagement_event_count = Event.search_count([
                ('partner_id', '=', partner.id), ('active', '=', True),
            ])

    def action_open_engagement_events(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Eventos del cliente',
            'res_model': 'crm.engagement.event',
            'view_mode': 'list,form',
            'domain': [('partner_id', '=', self.id)],
            'context': {'default_partner_id': self.id},
        }

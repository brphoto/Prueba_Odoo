# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class CrmEngagementEvent(models.Model):
    _name = 'crm.engagement.event'
    _description = 'Evento comercial del cliente'
    _order = 'event_date, id'

    name = fields.Char(string='Evento', required=True)
    partner_id = fields.Many2one('res.partner', string='Cliente', required=True,
                                  ondelete='cascade', index=True)
    event_date = fields.Date(string='Fecha del evento', required=True, index=True)
    event_type = fields.Selection([
        ('plan', 'Plan o plazo'),
        ('renewal', 'Renovación'),
        ('contract', 'Contrato'),
        ('appointment', 'Cita'),
        ('installment', 'Cuota'),
        ('other', 'Otro'),
    ], string='Tipo', default='other', required=True)
    lead_id = fields.Many2one('crm.lead', string='Oportunidad', ondelete='set null')
    description = fields.Text(string='Detalle para el mensaje')
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', string='Compañía', related='partner_id.company_id',
        store=True, readonly=True)

    def name_get(self):
        return [(event.id, '%s - %s' % (event.name, event.event_date)) for event in self]

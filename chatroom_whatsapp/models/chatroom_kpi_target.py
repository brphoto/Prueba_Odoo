# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ChatroomKpiTarget(models.Model):
    _name = 'chatroom.kpi.target'
    _inherit = ['kpi.target.mixin', 'mail.thread', 'mail.activity.mixin']
    _description = 'Objetivo de KPI de Chatroom'
    _order = 'kpi_id, scope_type, id'

    kpi_id = fields.Many2one('chatroom.kpi.definition', required=True, ondelete='cascade')
    scope_type = fields.Selection(selection_add=[
        ('agent', 'Agente'), ('line', 'Línea de WhatsApp'),
    ], ondelete={'agent': 'set default', 'line': 'set default'})
    user_id = fields.Many2one('res.users', string='Agente')
    whatsapp_number_id = fields.Many2one('chatroom.whatsapp.number', string='Línea')

    @api.constrains('scope_type', 'user_id', 'whatsapp_number_id')
    def _check_scope(self):
        for record in self:
            if record.scope_type == 'agent' and not record.user_id:
                raise ValidationError(_('Selecciona el agente del objetivo.'))
            if record.scope_type == 'line' and not record.whatsapp_number_id:
                raise ValidationError(_('Selecciona la línea de WhatsApp del objetivo.'))

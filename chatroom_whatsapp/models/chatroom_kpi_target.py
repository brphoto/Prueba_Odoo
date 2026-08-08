# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ChatroomKpiTarget(models.Model):
    _name = 'chatroom.kpi.target'
    _description = 'Objetivo de KPI de Chatroom'
    _order = 'kpi_id, scope_type, id'

    kpi_id = fields.Many2one('chatroom.kpi.definition', required=True, ondelete='cascade')
    scope_type = fields.Selection([
        ('global', 'Global'), ('company', 'Compañía'),
        ('agent', 'Agente'), ('line', 'Línea de WhatsApp'),
    ], string='Alcance', required=True, default='global')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    user_id = fields.Many2one('res.users', string='Agente')
    whatsapp_number_id = fields.Many2one('chatroom.whatsapp.number', string='Línea')
    target_value = fields.Float(required=True)
    goal_direction = fields.Selection([
        ('higher', 'Mayor o igual'), ('lower', 'Menor o igual'),
    ], string='Cumplimiento', required=True, default='higher')
    active = fields.Boolean(default=True)

    @api.constrains('scope_type', 'company_id', 'user_id', 'whatsapp_number_id')
    def _check_scope(self):
        for record in self:
            if record.scope_type == 'agent' and not record.user_id:
                raise ValidationError('Selecciona el agente del objetivo.')
            if record.scope_type == 'line' and not record.whatsapp_number_id:
                raise ValidationError('Selecciona la línea de WhatsApp del objetivo.')

# -*- coding: utf-8 -*-
from odoo import fields, models


class ChatroomAuditLog(models.Model):
    _name = 'chatroom.audit.log'
    _description = 'Auditoría de conversaciones Chatroom'
    _order = 'change_date desc, id desc'

    channel_id = fields.Many2one('chatroom.channel', required=True, ondelete='cascade', index=True)
    change_date = fields.Datetime(string='Fecha', required=True, default=fields.Datetime.now, index=True)
    user_id = fields.Many2one('res.users', string='Usuario', required=True, default=lambda self: self.env.user)
    change_type = fields.Selection([
        ('stage', 'Etapa'), ('state', 'Estado'), ('assigned_user', 'Responsable'),
        ('line', 'Línea'), ('urgent', 'Urgencia'),
    ], string='Cambio', required=True)
    old_value = fields.Char(string='Valor anterior')
    new_value = fields.Char(string='Valor nuevo')
    note = fields.Char(string='Detalle')

    def action_open_channel(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': self.channel_id.display_name,
            'res_model': 'chatroom.channel', 'res_id': self.channel_id.id,
            'views': [[False, 'form']], 'target': 'current',
        }

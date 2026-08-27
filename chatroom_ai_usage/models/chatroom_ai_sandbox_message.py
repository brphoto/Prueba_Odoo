# -*- coding: utf-8 -*-
from odoo import fields, models


class ChatroomAiSandboxMessage(models.Model):
    _name = 'chatroom.ai.sandbox.message'
    _description = 'Mensaje del laboratorio de conversación IA'
    _order = 'sequence, id'

    sandbox_id = fields.Many2one(
        'chatroom.ai.sandbox', string='Sesión de prueba', required=True,
        ondelete='cascade', index=True)
    sequence = fields.Integer(string='Orden', default=10)
    speaker = fields.Selection([
        ('customer', 'Cliente'), ('assistant', 'IA'),
    ], string='Interlocutor', required=True)
    body = fields.Text(string='Mensaje', required=True)
    message_date = fields.Datetime(string='Fecha', default=fields.Datetime.now, readonly=True)

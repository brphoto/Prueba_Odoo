# -*- coding: utf-8 -*-
from odoo import fields, models


class ChatroomAiQuickAction(models.Model):
    _inherit = 'chatroom.ai.quick.action'

    model_id = fields.Many2one(
        'chatroom.ai.provider.model', string='Modelo de IA',
        domain=[('active', '=', True), ('supports_chat', '=', True)],
        help='Modelo para esta acción. Vacío: el modelo por tarea de Ajustes. '
             'Útil para usar un modelo económico en clasificaciones y uno mejor '
             'en respuestas al cliente.')

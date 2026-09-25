# -*- coding: utf-8 -*-
from odoo import fields, models


class ChatroomWhatsappNumber(models.Model):
    _inherit = 'chatroom.whatsapp.number'

    ai_persona = fields.Text(
        string='Persona de la IA en esta línea',
        help='Cómo se presenta y habla la IA en las conversaciones de este número: '
             'marca, tono, qué ofrece y qué no debe prometer. Se agrega a todas '
             'las consultas de IA de la línea (sugerencias, acciones rápidas, agente).\n'
             'Ej.: «Eres el asistente de Tienda Norte. Tuteas al cliente, eres breve '
             'y solo hablas de productos de hogar. Nunca confirmes fechas de entrega.»')
    ai_quick_action_ids = fields.Many2many(
        'chatroom.ai.quick.action', 'chatroom_ai_quick_action_line_rel',
        'line_id', 'action_id', string='Acciones de IA exclusivas',
        help='Acciones que solo se ofrecen en esta línea. Las acciones sin '
             'líneas se ofrecen en todas.')

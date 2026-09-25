# -*- coding: utf-8 -*-
from odoo import fields, models

from odoo.addons.chatroom_ai_learning.models.learning_utils import CATEGORIES

EVENT_KINDS = [
    ('sent', 'Respondió sola'),
    ('local', 'Respuesta rápida'),
    ('approval', 'Borrador para aprobar'),
    ('review', 'Revisión humana'),
    ('handoff', 'Pasó a una persona'),
    ('followup', 'Seguimiento enviado'),
    ('skipped', 'Sin respuesta (pausa, límite...)'),
    ('error', 'Error'),
]


class ChatroomAiAgentEvent(models.Model):
    """Qué hizo el agente con cada mensaje: base del tablero."""
    _name = 'chatroom.ai.agent.event'
    _description = 'Actividad del agente IA'
    _order = 'create_date desc, id desc'
    _rec_name = 'kind'

    channel_id = fields.Many2one('chatroom.channel', string='Conversación', ondelete='set null', index=True)
    company_id = fields.Many2one('res.company', string='Empresa', default=lambda self: self.env.company,
                                 required=True, index=True)
    profile_id = fields.Many2one('chatroom.ai.agent.profile', string='Perfil', ondelete='set null', index=True)
    line_id = fields.Many2one('chatroom.whatsapp.number', string='Línea', ondelete='set null')
    kind = fields.Selection(EVENT_KINDS, string='Resultado', required=True, index=True)
    status = fields.Char(string='Estado técnico')
    reason = fields.Char(string='Motivo')
    intent = fields.Selection(CATEGORIES, string='Tipo de conversación')
    latency_ms = fields.Integer(string='Tiempo de respuesta (ms)', aggregator='avg')
    cost = fields.Float(string='Costo IA (USD)', digits=(16, 6), aggregator='sum')
    tokens = fields.Integer(string='Tokens', aggregator='sum')
    cached = fields.Boolean(string='Respuesta reutilizada')
    date = fields.Date(string='Día', default=fields.Date.context_today, index=True)

# -*- coding: utf-8 -*-
import json

from odoo import _, fields, models


class ChatroomAiAutonomyRequest(models.Model):
    _name = 'chatroom.ai.autonomy.request'
    _description = 'Evaluación y trazabilidad de autonomía IA'
    _order = 'create_date desc, id desc'

    name = fields.Char(string='Evaluación', required=True)
    channel_id = fields.Many2one('chatroom.channel', string='Conversación', ondelete='set null', index=True)
    partner_id = fields.Many2one(related='channel_id.partner_id', string='Cliente', store=True)
    policy_id = fields.Many2one('chatroom.ai.autonomy.policy', string='Política')
    action_key = fields.Selection([
        ('reply', 'Responder'), ('create_quotation', 'Crear cotización'),
        ('confirm_order', 'Confirmar pedido'), ('send_payment_link', 'Enviar link de pago'),
        ('notify_delivery', 'Notificar entrega'),
    ], string='Acción', required=True)
    amount = fields.Monetary(string='Monto', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    confidence = fields.Float(string='Confianza')
    decision = fields.Selection([
        ('allow', 'Permitida'), ('approval', 'Aprobación humana'), ('blocked', 'Bloqueada'),
    ], string='Decisión', required=True)
    reason = fields.Text(string='Motivo')
    query = fields.Text(string='Consulta')
    context_snapshot = fields.Text(string='Contexto usado')
    sources_json = fields.Text(string='Fuentes')
    estimated_tokens = fields.Integer(string='Tokens estimados')
    state = fields.Selection([
        ('simulated', 'Simulada'), ('executed', 'Ejecutada'), ('cancelled', 'Cancelada'),
    ], default='simulated', required=True)
    user_id = fields.Many2one('res.users', default=lambda self: self.env.user, required=True)

    def source_names(self):
        self.ensure_one()
        try:
            return [item.get('name') for item in json.loads(self.sources_json or '[]')]
        except (TypeError, ValueError):
            return []

    def action_mark_cancelled(self):
        self.write({'state': 'cancelled'})
        return True

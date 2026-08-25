# -*- coding: utf-8 -*-
from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ChatroomAiAutonomyPolicy(models.Model):
    _name = 'chatroom.ai.autonomy.policy'
    _description = 'Política de autonomía del agente IA'
    _order = 'sequence, name'

    name = fields.Char(string='Nombre de la política', required=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one(
        'res.company', string='Empresa', default=lambda self: self.env.company,
        required=True, index=True)
    mode = fields.Selection([
        ('assist', 'Asistente: prepara y sugiere'),
        ('approval', 'Controlado: requiere aprobación'),
        ('autonomous', 'Autónomo: permite acciones aprobadas'),
    ], string='Modo operativo', default='approval', required=True)
    allow_reply = fields.Boolean(string='Responder consultas', default=True)
    allow_quotation = fields.Boolean(string='Crear cotizaciones', default=True)
    allow_order = fields.Boolean(string='Confirmar pedidos', default=False)
    allow_payment = fields.Boolean(string='Enviar links de pago', default=False)
    allow_delivery = fields.Boolean(string='Notificar entregas', default=True)
    max_order_amount = fields.Monetary(
        string='Monto máximo por pedido', currency_field='currency_id', default=0.0)
    currency_id = fields.Many2one(
        'res.currency', related='company_id.currency_id', readonly=True)
    min_confidence = fields.Float(string='Confianza mínima', default=0.80)
    daily_message_limit = fields.Integer(string='Mensajes automáticos diarios', default=20)
    require_human_negative = fields.Boolean(string='Escalar sentimiento negativo', default=True)
    require_human_discount = fields.Boolean(string='Escalar descuentos', default=True)
    description = fields.Text(string='Criterio de uso')
    risk_level = fields.Selection([
        ('low', 'Bajo'), ('medium', 'Medio'), ('high', 'Alto'),
    ], string='Nivel de riesgo', compute='_compute_operational_summary')
    operational_summary = fields.Char(
        string='Resumen operativo', compute='_compute_operational_summary')

    @api.depends(
        'mode', 'allow_reply', 'allow_quotation', 'allow_order',
        'allow_payment', 'allow_delivery', 'max_order_amount',
        'require_human_negative', 'require_human_discount')
    def _compute_operational_summary(self):
        for policy in self:
            sensitive = policy.allow_order or policy.allow_payment
            if policy.mode == 'autonomous' and sensitive:
                policy.risk_level = 'high'
                policy.operational_summary = _(
                    'Autonomía controlada con acciones comerciales habilitadas.')
            elif policy.mode == 'approval' or policy.allow_quotation:
                policy.risk_level = 'medium'
                policy.operational_summary = _(
                    'La IA prepara acciones, pero las operaciones sensibles requieren aprobación.')
            else:
                policy.risk_level = 'low'
                policy.operational_summary = _(
                    'La IA funciona como asistente y no ejecuta operaciones sensibles.')

    @api.constrains('min_confidence', 'daily_message_limit', 'max_order_amount')
    def _check_operational_limits(self):
        for record in self:
            if not 0.0 <= record.min_confidence <= 1.0:
                raise ValidationError(_('La confianza mínima debe estar entre 0% y 100%.'))
            if record.daily_message_limit < 0:
                raise ValidationError(_('El límite diario no puede ser negativo.'))
            if record.max_order_amount < 0:
                raise ValidationError(_('El monto máximo no puede ser negativo.'))

    @api.model
    def get_active_policy(self, company=False):
        company = company or self.env.company
        return self.sudo().search([
            ('active', '=', True), ('company_id', '=', company.id),
        ], order='sequence, id', limit=1)

    def evaluate(self, action_key, amount=0.0, confidence=1.0, channel=False):
        self.ensure_one()
        allowed = {
            'reply': self.allow_reply,
            'create_quotation': self.allow_quotation,
            'confirm_order': self.allow_order,
            'send_payment_link': self.allow_payment,
            'notify_delivery': self.allow_delivery,
        }.get(action_key, False)
        if not allowed:
            return {'decision': 'blocked', 'reason': _('La política no permite esta acción.')}
        if confidence < self.min_confidence:
            return {'decision': 'approval', 'reason': _('La confianza %.0f%% está por debajo del mínimo %.0f%%.') % (confidence * 100, self.min_confidence * 100)}
        if action_key == 'reply' and self.daily_message_limit and channel and 'chatroom.message' in self.env:
            start = datetime.combine(fields.Date.context_today(self), datetime.min.time())
            sent_today = self.env['chatroom.message'].sudo().search_count([
                ('channel_id', '=', channel.id), ('direction', '=', 'outbound'),
                ('ai_generated', '=', True),
                ('date', '>=', fields.Datetime.to_string(start)),
            ]) if 'ai_generated' in self.env['chatroom.message']._fields else 0
            if sent_today >= self.daily_message_limit:
                return {'decision': 'approval', 'reason': _('Se alcanzó el límite diario de respuestas automáticas (%s).') % self.daily_message_limit}
        if action_key in ('confirm_order', 'send_payment_link') and self.max_order_amount and amount > self.max_order_amount:
            return {'decision': 'approval', 'reason': _('El monto supera el límite autorizado de %s.') % self.max_order_amount}
        if self.mode in ('assist', 'approval') and action_key in ('confirm_order', 'send_payment_link', 'create_quotation'):
            return {'decision': 'approval', 'reason': _('La política exige aprobación humana para acciones comerciales.')}
        return {'decision': 'allow', 'reason': _('Acción autorizada por la política.')}

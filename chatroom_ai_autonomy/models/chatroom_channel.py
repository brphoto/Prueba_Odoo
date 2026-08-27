# -*- coding: utf-8 -*-
import re

from odoo import _, fields, models


class ChatroomChannel(models.Model):
    _inherit = 'chatroom.channel'

    autonomy_policy_id = fields.Many2one(
        'chatroom.ai.autonomy.policy', string='Política de autonomía', copy=False)

    def _autonomy_capture_memory(self, message):
        """Capture only explicit customer preferences; no AI call is used."""
        self.ensure_one()
        if 'chatroom.ai.memory' not in self.env or not message or message.direction != 'inbound':
            return False
        body = re.sub(r'\s+', ' ', (message.body or '').strip())
        if not body:
            return False
        patterns = [
            (r'\b(prefiero|preferimos)\s+(.{3,160})', 'preference'),
            (r'\b(mi horario es|atien(?:do|demos) de)\s+(.{3,120})', 'preference'),
            (r'\b(entregar|entrega)\s+(?:en|a)\s+(.{3,160})', 'commitment'),
            (r'\b(no me llam(?:en|es)|no llamar)\b', 'preference'),
        ]
        for pattern, memory_type in patterns:
            if re.search(pattern, body, re.IGNORECASE):
                return self.env['chatroom.ai.memory'].sudo().remember(
                    body[:300], partner=self.partner_id, channel=self,
                    memory_type=memory_type, source='conversation', importance='2')
        return False

    def _ai_process_inbound_message(self, message):
        self._autonomy_capture_memory(message)
        return super()._ai_process_inbound_message(message)

    def get_ai_assistant_data(self):
        data = super().get_ai_assistant_data()
        policy = self.autonomy_policy_id or self.env['chatroom.ai.autonomy.policy'].get_active_policy(
            self.company_id, channel=self, partner=self.partner_id)
        profile = self.env['chatroom.ai.knowledge.profile'].sudo().search([
            ('company_id', '=', self.company_id.id), ('active', '=', True),
            ('state', '=', 'ready'),
        ], order='sequence, id', limit=1)
        data.update({
            'autonomy': {
                'policy_name': policy.name if policy else '',
                'mode': policy.mode if policy else 'approval',
                'knowledge_profile': profile.name if profile else '',
                'knowledge_sources': profile.source_summary if profile else '',
                'memory_count': self.env['chatroom.ai.memory'].sudo().search_count([
                    ('active', '=', True),
                    '|', ('channel_id', '=', self.id), ('partner_id', '=', self.partner_id.id or 0),
                ]) if 'chatroom.ai.memory' in self.env else 0,
            },
        })
        return data

    def _ai_deliver_guarded_reply(self, reply, confidence, intent=False, reason=False):
        """Apply the optional autonomy policy to automatic replies."""
        self.ensure_one()
        policy = self.autonomy_policy_id or self.env['chatroom.ai.autonomy.policy'].get_active_policy(
            self.company_id, channel=self, partner=self.partner_id)
        if policy:
            result = policy.evaluate('reply', confidence=confidence, channel=self)
            if result['decision'] != 'allow':
                decision = 'human_review' if result['decision'] == 'approval' else 'blocked'
                suggestion = self._ai_create_guarded_suggestion(
                    reply, confidence, decision, result['reason'], intent=intent)
                if 'chatroom.ai.autonomy.exception' in self.env:
                    exception_model = self.env['chatroom.ai.autonomy.exception'].sudo()
                    existing = exception_model.search([
                        ('channel_id', '=', self.id),
                        ('exception_type', '=', 'approval' if decision == 'human_review' else 'blocked'),
                        ('state', 'in', ('open', 'in_progress')),
                    ], limit=1)
                    if not existing:
                        exception_model.create({
                            'name': _('Intervención requerida: %s') % self.display_name,
                            'channel_id': self.id, 'partner_id': self.partner_id.id,
                            'exception_type': 'approval' if decision == 'human_review' else 'blocked',
                            'severity': 'medium' if decision == 'human_review' else 'high',
                            'reason': result['reason'],
                            'recommended_action': _('Revisar la sugerencia antes de responder al cliente.'),
                        })
                return {
                    'status': 'awaiting_approval' if decision == 'human_review' else 'blocked',
                    'suggestion_id': suggestion.id, 'reason': result['reason'],
                }
        return super()._ai_deliver_guarded_reply(
            reply, confidence, intent=intent, reason=reason)

    def _autonomy_evaluate(self, action_key, amount=0.0, confidence=1.0):
        self.ensure_one()
        policy = self.autonomy_policy_id or self.env['chatroom.ai.autonomy.policy'].get_active_policy(
            self.company_id, channel=self, partner=self.partner_id)
        if not policy:
            return {'decision': 'approval', 'reason': _('No hay una política activa de autonomía.')}
        return policy.evaluate(action_key, amount=amount, confidence=confidence, channel=self)

    def _sales_after_checkout(self, order):
        """Apply the optional autonomy policy before any irreversible sale action.

        The bridge stays inert when no policy is active, preserving the existing
        sales configuration. Once a policy is active, confirmation and payment
        are evaluated together so the agent cannot confirm a sale and then send
        a payment link outside the configured approval boundary.
        """
        self.ensure_one()
        if not self._sales_param_enabled('chatroom_ai_sales.auto_confirm'):
            return super()._sales_after_checkout(order)
        policy = self.autonomy_policy_id or self.env['chatroom.ai.autonomy.policy'].get_active_policy(
            self.company_id, channel=self, partner=self.partner_id)
        if not policy:
            return super()._sales_after_checkout(order)
        confirmation = policy.evaluate('confirm_order', amount=order.amount_total, channel=self)
        payment = {'decision': 'allow'}
        if self._sales_param_enabled('chatroom_ai_sales.auto_payment_link'):
            payment = policy.evaluate('send_payment_link', amount=order.amount_total, channel=self)
        if confirmation['decision'] != 'allow' or payment['decision'] != 'allow':
            reasons = [item['reason'] for item in (confirmation, payment) if item['decision'] != 'allow']
            reason = ' '.join(dict.fromkeys(reasons))
            self.ai_sales_status = 'escalated'
            self.ai_sales_last_order_id = order.id
            self.ai_sales_last_error = reason
            self.ai_sales_reply_override = reason + ' ' + _('Un asesor debe continuar esta operación.')
            self._sales_log('blocked', reason, order=order)
            self.env['chatroom.ai.autonomy.request'].sudo().create({
                'name': _('Venta retenida: %s') % self.display_name,
                'channel_id': self.id,
                'policy_id': policy.id,
                'action_key': 'confirm_order',
                'amount': order.amount_total,
                'currency_id': order.currency_id.id,
                'confidence': 1.0,
                'decision': 'approval' if any(item['decision'] == 'approval' for item in (confirmation, payment)) else 'blocked',
                'reason': reason,
                'query': _('Checkout automático con política activa'),
                'state': 'simulated',
            })
            return
        return super()._sales_after_checkout(order)

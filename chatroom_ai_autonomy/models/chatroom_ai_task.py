# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ChatroomAiTaskAutonomy(models.Model):
    """Connects the agent task engine with the autonomy policy.

    The task engine remains reusable and the policy module is the only layer
    that decides whether a sensitive action can run automatically.
    """

    _inherit = 'chatroom.ai.task'

    autonomy_policy_id = fields.Many2one(
        'chatroom.ai.autonomy.policy', string='Política aplicada',
        compute='_compute_autonomy_context', readonly=True)
    autonomy_decision = fields.Selection([
        ('not_evaluated', 'No evaluada'),
        ('allow', 'Autorizada por política'),
        ('approval', 'Requiere aprobación'),
        ('blocked', 'Bloqueada'),
    ], string='Decisión de autonomía', default='not_evaluated', readonly=True)
    autonomy_reason = fields.Text(string='Motivo de autonomía', readonly=True)
    autonomy_confidence = fields.Float(string='Confianza evaluada', readonly=True)
    autonomy_evaluated_at = fields.Datetime(string='Evaluada el', readonly=True)

    @api.depends('channel_id', 'partner_id', 'company_id')
    def _compute_autonomy_context(self):
        for task in self:
            task.autonomy_policy_id = task._autonomy_policy()

    def _autonomy_policy(self):
        self.ensure_one()
        if 'chatroom.ai.autonomy.policy' not in self.env:
            return self.env['chatroom.ai.autonomy.policy'].browse()
        return self.env['chatroom.ai.autonomy.policy'].get_active_policy(
            self.company_id or self.env.company,
            channel=self.channel_id,
            partner=self.partner_id)

    def _autonomy_action_key(self, action):
        return {
            'send_whatsapp_reply': 'reply',
            'create_lead': 'create_lead',
            'create_activity': 'create_activity',
            'create_quotation': 'create_quotation',
            'send_payment_link': 'send_payment_link',
        }.get(action.key)

    def _autonomy_confidence(self, policy):
        self.ensure_one()
        if self.channel_id and 'chatroom.ai.suggestion' in self.env:
            suggestion = self.env['chatroom.ai.suggestion'].sudo().search([
                ('channel_id', '=', self.channel_id.id),
                ('confidence', '>', 0),
            ], order='create_date desc, id desc', limit=1)
            if suggestion:
                return min(max(suggestion.confidence, 0.0), 1.0)
        # A local, deterministic plan has no model uncertainty. Use the
        # policy threshold itself, so the administrator controls the gate.
        return policy.min_confidence if policy else 0.0

    def _autonomy_action_amount(self, action_key):
        self.ensure_one()
        if action_key not in ('create_quotation', 'send_payment_link', 'confirm_order'):
            return 0.0
        channel = self.channel_id
        if channel and 'ai_sales_last_order_id' in channel._fields and channel.ai_sales_last_order_id:
            return channel.ai_sales_last_order_id.amount_total
        if self.partner_id and 'sale.order' in self.env:
            order = self.env['sale.order'].search([
                ('partner_id', '=', self.partner_id.id),
                ('state', 'in', ('draft', 'sent', 'sale')),
                ('company_id', '=', self.company_id.id),
            ], order='date_order desc, id desc', limit=1)
            if order:
                return order.amount_total
        if self.partner_id and 'account.move' in self.env:
            invoice = self.env['account.move'].search([
                ('partner_id', '=', self.partner_id.id),
                ('move_type', '=', 'out_invoice'), ('state', '=', 'posted'),
                ('payment_state', 'in', ('not_paid', 'partial')),
                ('company_id', '=', self.company_id.id),
            ], order='invoice_date desc, id desc', limit=1)
            if invoice:
                return invoice.amount_residual
        return 0.0

    def _autonomy_trace(self, policy, action_key, result, amount, confidence):
        self.ensure_one()
        if 'chatroom.ai.autonomy.request' not in self.env:
            return False
        return self.env['chatroom.ai.autonomy.request'].sudo().create({
            'name': _('Tarea %s: %s') % (self.display_name, action_key),
            'task_id': self.id,
            'channel_id': self.channel_id.id if self.channel_id else False,
            'policy_id': policy.id,
            'action_key': action_key,
            'amount': amount,
            'currency_id': self.company_id.currency_id.id,
            'confidence': confidence,
            'decision': result['decision'],
            'reason': result['reason'],
            'query': self.prompt,
            'context_snapshot': self.input_context,
            'estimated_tokens': 0,
            'state': 'simulated',
        })

    def _autonomy_apply_to_plan(self, requested_approval=True):
        self.ensure_one()
        policy = self._autonomy_policy()
        if not policy:
            self.write({
                'autonomy_decision': 'not_evaluated',
                'autonomy_reason': _('No existe una política activa para este canal o cliente.'),
                'autonomy_evaluated_at': fields.Datetime.now(),
            })
            return False
        confidence = self._autonomy_confidence(policy)
        decisions = []
        for action in self.action_ids.filtered(lambda line: line.state in ('pending', 'error')):
            action_key = self._autonomy_action_key(action)
            if not action_key:
                continue
            amount = self._autonomy_action_amount(action_key)
            result = policy.evaluate(action_key, amount=amount, confidence=confidence, channel=self.channel_id)
            decisions.append(result['decision'])
            self._autonomy_trace(policy, action_key, result, amount, confidence)
        decision = 'allow'
        if 'blocked' in decisions:
            decision = 'blocked'
        elif 'approval' in decisions:
            decision = 'approval'
        reason = _('Todas las acciones sensibles están autorizadas por la política autónoma.')
        if decision == 'approval':
            reason = _('Una o más acciones necesitan aprobación humana según sus límites.')
        elif decision == 'blocked':
            reason = _('Una o más acciones están bloqueadas por la política de seguridad.')
        if requested_approval and decision == 'allow':
            decision = 'approval'
            reason = _('La política permite la operación, pero esta tarea conserva una aprobación explícita.')
        values = {
            'autonomy_decision': decision,
            'autonomy_reason': reason,
            'autonomy_confidence': confidence,
            'autonomy_evaluated_at': fields.Datetime.now(),
        }
        if policy.mode == 'autonomous' and decision == 'allow':
            # The policy is the per-task approval gate. It does not modify the
            # global tool definition; it only authorizes this concrete task.
            self.action_ids.filtered(lambda line: self._autonomy_action_key(line)).write({
                'requires_approval': False,
            })
            values.update({'approval_required': False, 'state': 'planned', 'error_message': False})
        elif decision in ('approval', 'blocked'):
            values.update({'approval_required': True, 'state': 'awaiting_approval', 'error_message': reason})
        self.write(values)
        self._audit('Autonomía evaluada', 'done', message=reason)
        return decision == 'allow'

    def action_plan(self):
        requested = {task.id: task.approval_required for task in self}
        result = super().action_plan()
        for task in self:
            if task.state in ('awaiting_approval', 'planned') and task.action_ids:
                task._autonomy_apply_to_plan(requested.get(task.id, True))
        return result

    def _autonomy_guard_before_run(self):
        self.ensure_one()
        policy = self._autonomy_policy()
        if not policy or self.approved_by:
            return
        if policy.mode != 'autonomous':
            self.write({
                'approval_required': True,
                'state': 'awaiting_approval',
                'autonomy_decision': 'approval',
                'autonomy_reason': _('La política actual no permite ejecución autónoma.'),
            })
            raise UserError(_('La política actual requiere aprobación humana antes de ejecutar esta tarea.'))
        if self.autonomy_decision != 'allow':
            self._autonomy_apply_to_plan(False)
        if self.autonomy_decision != 'allow':
            raise UserError(self.autonomy_reason or _('La política de autonomía no autorizó esta tarea.'))

    def action_run(self):
        for task in self:
            if task.state in ('draft', 'planned', 'failed'):
                task._autonomy_guard_before_run()
        return super().action_run()

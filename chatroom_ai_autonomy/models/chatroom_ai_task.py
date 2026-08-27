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
    verification_state = fields.Selection([
        ('pending', 'Pendiente'), ('verified', 'Verificado'),
        ('warning', 'Revisión requerida'),
    ], string='Verificación del resultado', default='pending', readonly=True)
    verification_message = fields.Text(string='Resultado de verificación', readonly=True)
    next_action = fields.Char(string='Próxima acción sugerida', readonly=True)
    next_task_type = fields.Selection([
        ('followup', 'Seguimiento'), ('collect_payment', 'Cobranza'),
        ('prepare_reply', 'Preparar respuesta'),
    ], string='Tipo de siguiente tarea', readonly=True)
    needs_human = fields.Boolean(string='Requiere intervención humana', readonly=True)
    chain_parent_id = fields.Many2one(
        'chatroom.ai.task', string='Tarea anterior', readonly=True, ondelete='set null')
    chain_step = fields.Integer(string='Paso del flujo', default=0, readonly=True)

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

    def _autonomy_exception(self, exception_type, reason, recommended=False, severity='medium'):
        self.ensure_one()
        if 'chatroom.ai.autonomy.exception' not in self.env:
            return False
        existing = self.env['chatroom.ai.autonomy.exception'].sudo().search([
            ('task_id', '=', self.id), ('state', 'in', ('open', 'in_progress')),
            ('exception_type', '=', exception_type),
        ], limit=1)
        if existing:
            return existing
        return self.env['chatroom.ai.autonomy.exception'].sudo().create({
            'name': _('Revisión: %s') % self.display_name,
            'task_id': self.id,
            'channel_id': self.channel_id.id if self.channel_id else False,
            'partner_id': self.partner_id.id if self.partner_id else False,
            'policy_id': self.autonomy_policy_id.id if self.autonomy_policy_id else False,
            'exception_type': exception_type,
            'severity': severity,
            'reason': reason,
            'recommended_action': recommended or _('Revisar la conversación y decidir si se aprueba, edita o reintenta.'),
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
        if decision == 'approval':
            self._autonomy_exception(
                'approval', reason,
                _('Revisar el plan, aprobarlo si corresponde y ejecutar la tarea.'), 'medium')
        elif decision == 'blocked':
            self._autonomy_exception(
                'blocked', reason,
                _('Ajustar la política o continuar manualmente desde la conversación.'), 'high')
        return decision == 'allow'

    def action_plan(self):
        requested = {task.id: task.approval_required for task in self}
        result = super().action_plan()
        for task in self:
            if task.state in ('awaiting_approval', 'planned') and task.action_ids:
                task._autonomy_apply_to_plan(requested.get(task.id, True))
        return result

    def _autonomy_verify_result(self):
        """Verify that important tools left a usable Odoo result."""
        self.ensure_one()
        if self.state != 'done':
            return
        try:
            import json
            outputs = json.loads(self.output_json or '[]')
        except (TypeError, ValueError):
            outputs = []
        warnings = []
        next_action = _('Revisar el resultado de la tarea.')
        next_type = False
        for output in outputs:
            if output.get('status') == 'blocked':
                warnings.append(output.get('reason') or _('Una acción fue bloqueada.'))
            if output.get('lead_id') and 'crm.lead' in self.env and not self.env['crm.lead'].browse(output['lead_id']).exists():
                warnings.append(_('La oportunidad reportada ya no existe.'))
            if output.get('order_id') and 'sale.order' in self.env and not self.env['sale.order'].browse(output['order_id']).exists():
                warnings.append(_('La cotización reportada ya no existe.'))
            if output.get('link_id') and 'chatroom.payment.link' in self.env and not self.env['chatroom.payment.link'].browse(output['link_id']).exists():
                warnings.append(_('El enlace de pago reportado ya no existe.'))
            if output.get('reply'):
                next_action = _('Revisar y enviar la respuesta preparada.')
                next_type = 'prepare_reply'
            elif output.get('link_id'):
                next_action = _('Verificar el pago y continuar el seguimiento.')
                next_type = 'collect_payment'
            elif output.get('order_name'):
                next_action = _('Dar seguimiento a la cotización %s.') % output['order_name']
                next_type = 'followup'
            elif output.get('lead_name'):
                next_action = _('Dar seguimiento a la oportunidad %s.') % output['lead_name']
                next_type = 'followup'
            elif output.get('invoices') is not None and output.get('invoices'):
                next_action = _('Enviar recordatorio de cobranza y revisar el saldo.')
                next_type = 'collect_payment'
        if next_type == self.task_type:
            next_type = False
        if warnings:
            message = ' '.join(dict.fromkeys(warnings))
            self.write({
                'verification_state': 'warning',
                'verification_message': message,
                'needs_human': True,
                'next_action': _('Revisar la excepción antes de continuar.'),
                'next_task_type': False,
            })
            self._autonomy_exception('verification', message, next_action, 'high')
        else:
            self.write({
                'verification_state': 'verified',
                'verification_message': _('Las salidas importantes fueron verificadas en Odoo.'),
                'needs_human': False,
                'next_action': next_action,
                'next_task_type': next_type,
            })
            policy = self._autonomy_policy()
            if policy and policy.mode == 'autonomous' and policy.auto_continue and next_type:
                self._autonomy_continue(next_type, next_action, policy)

    def _autonomy_continue(self, task_type, prompt, policy):
        self.ensure_one()
        if self.chain_step >= policy.max_chain_steps:
            self._autonomy_exception(
                'verification',
                _('El flujo alcanzó el máximo de %s pasos autónomos.') % policy.max_chain_steps,
                _('Revisar el resultado y continuar manualmente si corresponde.'), 'medium')
            return False
        next_task = self.env['chatroom.ai.task'].sudo().create_from_channel(
            self.channel_id, task_type=task_type, prompt=prompt,
            approval_required=False)
        next_task.write({'chain_parent_id': self.id, 'chain_step': self.chain_step + 1})
        next_task.action_plan()
        if next_task.state == 'planned':
            next_task.action_run()
        return next_task

    def action_create_next_task(self):
        self.ensure_one()
        if not self.channel_id or not self.next_task_type:
            raise UserError(_('Esta tarea no tiene una siguiente acción automática disponible.'))
        task = self.env['chatroom.ai.task'].create_from_channel(
            self.channel_id, task_type=self.next_task_type,
            prompt=self.next_action, approval_required=True)
        task.action_plan()
        return {
            'type': 'ir.actions.act_window', 'name': _('Siguiente tarea IA'),
            'res_model': 'chatroom.ai.task', 'res_id': task.id,
            'view_mode': 'form', 'target': 'current',
        }

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
        result = super().action_run()
        for task in self:
            task._autonomy_verify_result()
        return result

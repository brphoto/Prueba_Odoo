# -*- coding: utf-8 -*-
import json

from odoo import _, api, fields, models


class ChatroomAiAutonomySimulator(models.TransientModel):
    _name = 'chatroom.ai.autonomy.simulator'
    _description = 'Simulador seguro de conocimiento y autonomía IA'

    channel_id = fields.Many2one('chatroom.channel', string='Conversación')
    query = fields.Text(string='Pregunta o situación', required=True)
    action_key = fields.Selection([
        ('reply', 'Responder'), ('create_quotation', 'Crear cotización'),
        ('confirm_order', 'Confirmar pedido'), ('send_payment_link', 'Enviar link de pago'),
        ('notify_delivery', 'Notificar entrega'),
    ], string='Acción a evaluar', default='reply', required=True)
    amount = fields.Monetary(string='Monto de referencia', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    confidence = fields.Float(string='Confianza estimada', default=0.90)
    decision = fields.Selection([
        ('allow', 'Permitida'), ('approval', 'Aprobación humana'), ('blocked', 'Bloqueada'),
    ], readonly=True)
    reason = fields.Text(string='Resultado', readonly=True)
    context_preview = fields.Text(string='Contexto que recibiría la IA', readonly=True)
    sources = fields.Text(string='Fuentes utilizadas', readonly=True)
    estimated_tokens = fields.Integer(string='Tokens estimados', readonly=True)
    request_id = fields.Many2one('chatroom.ai.autonomy.request', readonly=True)
    simulation_message = fields.Char(
        string='Lectura de la simulación', compute='_compute_simulation_message')

    @api.depends('decision', 'estimated_tokens', 'request_id')
    def _compute_simulation_message(self):
        for simulator in self:
            if not simulator.decision:
                simulator.simulation_message = _(
                    'Escribe una pregunta y pulsa «Simular sin enviar» para evaluar la política.')
            elif simulator.decision == 'allow':
                simulator.simulation_message = _(
                    'La política permite esta acción. La simulación no envió mensajes ni modificó Odoo (%s tokens estimados).') % simulator.estimated_tokens
            elif simulator.decision == 'approval':
                simulator.simulation_message = _(
                    'La acción requiere aprobación humana. La simulación no ejecutó ninguna operación (%s tokens estimados).') % simulator.estimated_tokens
            else:
                simulator.simulation_message = _(
                    'La política bloquea esta acción. La simulación no ejecutó ninguna operación.')

    def action_simulate(self):
        self.ensure_one()
        channel = self.channel_id
        company = channel.company_id if channel else self.env.company
        details = self.env['ai.knowledge.base'].sudo().get_sales_context_details(
            channel=channel, query=self.query or '', company=company)
        policy = self.env['chatroom.ai.autonomy.policy'].get_active_policy(company)
        if policy:
            result = policy.evaluate(self.action_key, self.amount, self.confidence, channel=channel)
        else:
            result = {'decision': 'approval', 'reason': _('No existe una política activa; la acción queda pendiente de configuración.')}
        request = self.env['chatroom.ai.autonomy.request'].create({
            'name': _('Simulación: %s') % (self.query or '')[:80],
            'channel_id': channel.id if channel else False,
            'policy_id': policy.id if policy else False,
            'action_key': self.action_key,
            'amount': self.amount,
            'currency_id': self.currency_id.id,
            'confidence': self.confidence,
            'decision': result['decision'],
            'reason': result['reason'],
            'query': self.query,
            'context_snapshot': details.get('context', ''),
            'sources_json': json.dumps(details.get('sources', []), ensure_ascii=False),
            'estimated_tokens': details.get('estimated_input_tokens', 0),
        })
        self.write({
            'decision': result['decision'], 'reason': result['reason'],
            'context_preview': details.get('context', ''),
            'sources': ', '.join(item.get('name', '') for item in details.get('sources', [])) or _('Fuentes vivas de Odoo'),
            'estimated_tokens': details.get('estimated_input_tokens', 0),
            'request_id': request.id,
        })
        return True

    def action_open_request(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _('Evaluación de autonomía'),
            'res_model': 'chatroom.ai.autonomy.request', 'view_mode': 'form',
            'res_id': self.request_id.id, 'target': 'new',
        }

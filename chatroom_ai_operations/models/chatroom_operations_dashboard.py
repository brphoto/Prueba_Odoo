# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class ChatroomOperationsDashboard(models.TransientModel):
    _name = 'chatroom.operations.dashboard'
    _description = 'Panel operativo de Chatroom'

    refreshed_at = fields.Datetime(string='Actualizado', readonly=True)
    active_conversations = fields.Integer(string='Conversaciones activas', readonly=True)
    sla_attention = fields.Integer(string='SLA por atender', readonly=True)
    abandoned_carts = fields.Integer(string='Carritos abandonados', readonly=True)
    failed_payments = fields.Integer(string='Pagos fallidos', readonly=True)
    pending_payments = fields.Integer(string='Pagos pendientes', readonly=True)
    deliveries_pending = fields.Integer(string='Entregas en curso', readonly=True)
    deliveries_late = fields.Integer(string='Entregas atrasadas', readonly=True)
    ai_pending = fields.Integer(string='Tareas IA pendientes', readonly=True)
    ai_approvals = fields.Integer(string='Aprobaciones IA', readonly=True)
    ai_failed = fields.Integer(string='Tareas IA fallidas', readonly=True)
    unread_notifications = fields.Integer(string='Alertas sin leer', readonly=True)
    demo_count = fields.Integer(string='Escenarios DEMO QA', readonly=True)
    summary = fields.Char(string='Estado general', readonly=True)

    @api.model
    def action_open_dashboard(self):
        record = self.create({})
        record._refresh_metrics()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Panel operativo'),
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': record.id,
            'target': 'current',
        }

    def _count(self, model_name, domain):
        if model_name not in self.env:
            return 0
        return self.env[model_name].sudo().search_count(domain)

    def _sla_channel_ids(self):
        Channel = self.env['chatroom.channel'].sudo()
        channels = Channel.search([('state', 'in', ('open', 'pending'))])
        return channels.filtered(
            lambda channel: channel.first_response_sla_state in ('yellow', 'red')
        ).ids

    def _refresh_metrics(self):
        for record in self:
            record.refreshed_at = fields.Datetime.now()
            record.active_conversations = self._count('chatroom.channel', [('state', 'in', ('open', 'pending'))])
            record.sla_attention = len(record._sla_channel_ids())
            record.abandoned_carts = self._count('chatroom.channel', [
                ('state', 'in', ('open', 'pending')),
                ('cart_line_ids', '!=', False),
                ('ai_sales_cart_reminder_count', '>', 0),
            ]) if 'ai_sales_cart_reminder_count' in self.env['chatroom.channel']._fields else 0
            record.failed_payments = self._count('chatroom.payment.link', [('state', '=', 'error')])
            record.pending_payments = self._count('chatroom.payment.link', [('state', 'in', ('generated', 'sent'))])
            record.deliveries_pending = self._count('stock.picking', [
                ('state', 'in', ('waiting', 'confirmed', 'assigned')),
                ('picking_type_code', '=', 'outgoing'),
            ])
            record.deliveries_late = self._count('stock.picking', [
                ('has_deadline_issue', '=', True),
                ('state', 'not in', ('done', 'cancel')),
            ])
            record.ai_pending = self._count('chatroom.ai.task', [('state', 'in', ('awaiting_approval', 'planned', 'running'))])
            record.ai_approvals = self._count('chatroom.ai.task', [('state', '=', 'awaiting_approval')])
            record.ai_failed = self._count('chatroom.ai.task', [('state', '=', 'failed')])
            record.unread_notifications = self._count('chatroom.notification', [('state', '=', 'unread')])
            record.demo_count = self._count('res.partner', [('name', 'like', 'DEMO QA - %')])
            critical = record.failed_payments + record.ai_failed + record.sla_attention
            record.summary = _('Revisión requerida: %s incidencia(s).') % critical if critical else _('Operación estable.')

    def action_refresh(self):
        self.ensure_one()
        self._refresh_metrics()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def _open(self, model, title, domain):
        return {
            'type': 'ir.actions.act_window', 'name': title, 'res_model': model,
            'view_mode': 'list,form', 'views': [(False, 'list'), (False, 'form')],
            'domain': domain, 'target': 'new',
        }

    def action_open_failed_payments(self):
        return self._open('chatroom.payment.link', _('Pagos fallidos'), [('state', '=', 'error')])

    def action_open_ai_failed(self):
        return self._open('chatroom.ai.task', _('Tareas IA fallidas'), [('state', '=', 'failed')])

    def action_open_sla(self):
        ids = self._sla_channel_ids()
        return self._open('chatroom.channel', _('Conversaciones con SLA'), [
            ('id', 'in', ids or [0]),
        ])

    def action_open_deliveries(self):
        return self._open('stock.picking', _('Entregas en curso'), [
            ('state', 'in', ('waiting', 'confirmed', 'assigned')), ('picking_type_code', '=', 'outgoing'),
        ])

    def action_open_notifications(self):
        return self._open('chatroom.notification', _('Alertas operativas'), [('state', '!=', 'done')])

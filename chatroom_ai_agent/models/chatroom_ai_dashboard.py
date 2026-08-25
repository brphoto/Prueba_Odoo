# -*- coding: utf-8 -*-
from datetime import datetime, timedelta

from odoo import _, api, fields, models


class ChatroomAiDashboard(models.Model):
    _name = 'chatroom.ai.dashboard'
    _description = 'Centro ejecutivo del agente IA'

    name = fields.Char(string='Panel', required=True, default='Centro ejecutivo IA')
    last_refresh = fields.Datetime(string='Última actualización', readonly=True)
    total_tasks = fields.Integer(string='Tareas totales', compute='_compute_metrics')
    pending_tasks = fields.Integer(string='Tareas pendientes', compute='_compute_metrics')
    approval_tasks = fields.Integer(string='Aprobaciones pendientes', compute='_compute_metrics')
    failed_tasks = fields.Integer(string='Tareas fallidas', compute='_compute_metrics')
    done_today = fields.Integer(string='Completadas hoy', compute='_compute_metrics')
    high_risk_tasks = fields.Integer(string='Alto riesgo', compute='_compute_metrics')
    active_automations = fields.Integer(string='Automatizaciones activas', compute='_compute_metrics')
    memory_count = fields.Integer(string='Memorias activas', compute='_compute_metrics')
    usage_requests = fields.Integer(string='Solicitudes IA recientes', compute='_compute_metrics')
    quality_pending = fields.Integer(string='Pruebas pendientes', compute='_compute_metrics')

    @api.depends('last_refresh')
    def _compute_metrics(self):
        now = fields.Datetime.to_datetime(fields.Datetime.now())
        start = datetime.combine(fields.Date.context_today(self), datetime.min.time())
        Task = self.env['chatroom.ai.task'].sudo()
        for dashboard in self:
            dashboard.total_tasks = Task.search_count([])
            dashboard.pending_tasks = Task.search_count([('state', 'in', ('awaiting_approval', 'planned', 'running'))])
            dashboard.approval_tasks = Task.search_count([('state', '=', 'awaiting_approval')])
            dashboard.failed_tasks = Task.search_count([('state', '=', 'failed')])
            dashboard.done_today = Task.search_count([('state', '=', 'done'), ('completed_at', '>=', start)])
            dashboard.high_risk_tasks = Task.search_count([('risk_level', '=', 'high'), ('state', 'not in', ('done', 'cancelled'))])
            dashboard.active_automations = self.env['chatroom.ai.automation'].sudo().search_count([('active', '=', True)]) if 'chatroom.ai.automation' in self.env else 0
            dashboard.memory_count = self.env['chatroom.ai.memory'].sudo().search_count([('active', '=', True)]) if 'chatroom.ai.memory' in self.env else 0
            dashboard.usage_requests = self.env['chatroom.ai.usage.event'].sudo().search_count([('request_date', '>=', now - timedelta(days=7))]) if 'chatroom.ai.usage.event' in self.env else 0
            dashboard.quality_pending = self.env['chatroom.ai.quality.test'].sudo().search_count([('active', '=', True), ('last_state', '=', 'pending')]) if 'chatroom.ai.quality.test' in self.env else 0

    def _open_task_action(self, domain, title):
        self.ensure_one()
        action = self.env.ref('chatroom_ai_agent.action_chatroom_ai_task', raise_if_not_found=False)
        if not action:
            return False
        result = action.read()[0]
        result.update({'name': title, 'domain': domain, 'context': {}})
        return result

    def action_open_pending(self):
        return self._open_task_action([('state', 'in', ('awaiting_approval', 'planned', 'running'))], _('Tareas pendientes'))

    def action_open_approvals(self):
        return self._open_task_action([('state', '=', 'awaiting_approval')], _('Aprobaciones pendientes'))

    def action_open_failed(self):
        return self._open_task_action([('state', '=', 'failed')], _('Tareas fallidas'))

    def action_open_high_risk(self):
        return self._open_task_action([('risk_level', '=', 'high'), ('state', 'not in', ('done', 'cancelled'))], _('Tareas de alto riesgo'))

    def action_open_quality(self):
        action = self.env.ref('chatroom_ai_usage.action_chatroom_ai_quality_test', raise_if_not_found=False)
        return action.read()[0] if action else self._notify(_('Pruebas de calidad'), _('Instala el módulo opcional de consumo de IA para usar esta sección.'), 'warning')

    def action_open_usage(self):
        action = self.env.ref('chatroom_ai_usage.action_chatroom_ai_usage_snapshot', raise_if_not_found=False)
        return action.read()[0] if action else self._notify(_('Consumo de IA'), _('Instala el módulo opcional de consumo de IA para ver esta sección.'), 'warning')

    def action_refresh(self):
        self.sudo().write({'last_refresh': fields.Datetime.now()})
        return self._notify(_('Centro ejecutivo IA'), _('Indicadores actualizados.'), 'success')

    @api.model
    def _notify(self, title, message, notification_type='info'):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': title, 'message': message, 'type': notification_type, 'sticky': False},
        }

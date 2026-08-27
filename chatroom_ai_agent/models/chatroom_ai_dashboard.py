# -*- coding: utf-8 -*-
from datetime import datetime, timedelta

from odoo import _, api, fields, models


class ChatroomAiDashboard(models.Model):
    _name = 'chatroom.ai.dashboard'
    _description = 'Centro ejecutivo del agente IA'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Panel', required=True, default='Centro ejecutivo IA')
    company_id = fields.Many2one(
        'res.company', string='Empresa', required=True,
        default=lambda self: self.env.company, index=True)
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
    suggestions_pending_feedback = fields.Integer(string='Respuestas sin valorar', compute='_compute_metrics')
    suggestions_unsafe = fields.Integer(string='Respuestas marcadas no usar', compute='_compute_metrics')
    ai_sent_today = fields.Integer(string='Mensajes IA hoy', compute='_compute_metrics')
    feedback_helpful = fields.Integer(string='Respuestas utiles', compute='_compute_metrics')
    feedback_edited = fields.Integer(string='Respuestas editadas', compute='_compute_metrics')
    feedback_unsafe = fields.Integer(string='Respuestas inseguras', compute='_compute_metrics')
    feedback_quality_percent = fields.Float(string='Calidad favorable (%)', compute='_compute_metrics')

    @api.model
    def _company_domain(self, model_name, domain, company):
        if model_name in self.env and 'company_id' in self.env[model_name]._fields:
            return list(domain) + [('company_id', '=', company.id)]
        return list(domain)

    @api.depends('last_refresh')
    def _compute_metrics(self):
        now = fields.Datetime.to_datetime(fields.Datetime.now())
        start = datetime.combine(fields.Date.context_today(self), datetime.min.time())
        Task = self.env['chatroom.ai.task'].sudo()
        for dashboard in self:
            company = dashboard.company_id or self.env.company
            task_domain = lambda domain: self._company_domain('chatroom.ai.task', domain, company)
            dashboard.total_tasks = Task.search_count(task_domain([]))
            dashboard.pending_tasks = Task.search_count(task_domain([('state', 'in', ('awaiting_approval', 'planned', 'running'))]))
            dashboard.approval_tasks = Task.search_count(task_domain([('state', '=', 'awaiting_approval')]))
            dashboard.failed_tasks = Task.search_count(task_domain([('state', '=', 'failed')]))
            dashboard.done_today = Task.search_count(task_domain([('state', '=', 'done'), ('completed_at', '>=', start)]))
            dashboard.high_risk_tasks = Task.search_count(task_domain([('risk_level', '=', 'high'), ('state', 'not in', ('done', 'cancelled'))]))
            dashboard.active_automations = self.env['chatroom.ai.automation'].sudo().search_count(self._company_domain('chatroom.ai.automation', [('active', '=', True)], company)) if 'chatroom.ai.automation' in self.env else 0
            dashboard.memory_count = self.env['chatroom.ai.memory'].sudo().search_count(self._company_domain('chatroom.ai.memory', [('active', '=', True)], company)) if 'chatroom.ai.memory' in self.env else 0
            dashboard.usage_requests = self.env['chatroom.ai.usage.event'].sudo().search_count(self._company_domain('chatroom.ai.usage.event', [('request_date', '>=', now - timedelta(days=7))], company)) if 'chatroom.ai.usage.event' in self.env else 0
            dashboard.quality_pending = self.env['chatroom.ai.quality.test'].sudo().search_count([('active', '=', True), ('last_state', '=', 'pending')]) if 'chatroom.ai.quality.test' in self.env else 0
            if 'chatroom.ai.suggestion' in self.env:
                suggestions = self.env['chatroom.ai.suggestion'].sudo()
                dashboard.suggestions_pending_feedback = suggestions.search_count([
                    ('state', 'in', ('approved', 'sent')), ('feedback_state', '=', 'pending'),
                    ('channel_id.company_id', '=', company.id),
                ])
                dashboard.feedback_helpful = suggestions.search_count([('feedback_state', '=', 'helpful'), ('channel_id.company_id', '=', company.id)])
                dashboard.feedback_edited = suggestions.search_count([('feedback_state', '=', 'edited'), ('channel_id.company_id', '=', company.id)])
                dashboard.feedback_unsafe = suggestions.search_count([('feedback_state', '=', 'unsafe'), ('channel_id.company_id', '=', company.id)])
                dashboard.suggestions_unsafe = dashboard.feedback_unsafe
                evaluated = dashboard.feedback_helpful + dashboard.feedback_edited + dashboard.feedback_unsafe
                dashboard.feedback_quality_percent = round(
                    dashboard.feedback_helpful / evaluated * 100.0, 2) if evaluated else 0.0
            else:
                dashboard.suggestions_pending_feedback = 0
                dashboard.suggestions_unsafe = 0
                dashboard.feedback_helpful = 0
                dashboard.feedback_edited = 0
                dashboard.feedback_unsafe = 0
                dashboard.feedback_quality_percent = 0.0
            dashboard.ai_sent_today = self.env['chatroom.message'].sudo().search_count([
                ('direction', '=', 'outbound'), ('ai_generated', '=', True),
                ('date', '>=', start),
                ('channel_id.company_id', '=', company.id),
            ]) if 'chatroom.message' in self.env and 'ai_generated' in self.env['chatroom.message']._fields else 0

    def _open_task_action(self, domain, title):
        self.ensure_one()
        action = self.env.ref('chatroom_ai_agent.action_chatroom_ai_task', raise_if_not_found=False)
        if not action:
            return False
        result = action.read()[0]
        result.update({
            'name': title,
            'domain': list(domain) + [('company_id', '=', self.company_id.id)],
            'context': {'default_company_id': self.company_id.id},
        })
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

    def action_open_suggestions(self):
        action = self.env.ref('chatroom_ai.action_chatroom_ai_suggestion', raise_if_not_found=False)
        if not action:
            return self._notify(_('Sugerencias IA'), _('Instala el modulo Chatroom IA para usar esta seccion.'), 'warning')
        result = action.read()[0]
        result.update({
            'name': _('Respuestas IA sin valorar'),
            'domain': [
                ('state', 'in', ('approved', 'sent')), ('feedback_state', '=', 'pending'),
                ('channel_id.company_id', '=', self.company_id.id),
            ],
        })
        return result

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

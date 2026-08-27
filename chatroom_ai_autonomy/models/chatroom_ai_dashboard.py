# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class ChatroomAiDashboardAutonomy(models.Model):
    _inherit = 'chatroom.ai.dashboard'

    open_exceptions = fields.Integer(string='Excepciones abiertas', compute='_compute_autonomy_metrics')
    autonomous_tasks = fields.Integer(string='Tareas autónomas', compute='_compute_autonomy_metrics')
    human_interventions = fields.Integer(string='Intervenciones humanas', compute='_compute_autonomy_metrics')
    autonomy_rate = fields.Float(string='Tasa autónoma (%)', compute='_compute_autonomy_metrics')

    @api.depends('last_refresh')
    def _compute_autonomy_metrics(self):
        for dashboard in self:
            company = dashboard.company_id or self.env.company
            if 'chatroom.ai.autonomy.exception' in self.env:
                dashboard.open_exceptions = self.env['chatroom.ai.autonomy.exception'].sudo().search_count([
                    ('state', 'in', ('open', 'in_progress')),
                    '|', ('channel_id.company_id', '=', company.id), ('channel_id', '=', False),
                ])
            else:
                dashboard.open_exceptions = 0
            tasks = self.env['chatroom.ai.task'].sudo().search([('company_id', '=', company.id)])
            dashboard.autonomous_tasks = len(tasks.filtered(lambda task: task.autonomy_decision == 'allow'))
            dashboard.human_interventions = len(tasks.filtered(lambda task: task.autonomy_decision == 'approval' or task.needs_human))
            evaluated = dashboard.autonomous_tasks + dashboard.human_interventions
            dashboard.autonomy_rate = round(dashboard.autonomous_tasks / evaluated * 100.0, 2) if evaluated else 0.0

    def action_open_exceptions(self):
        self.ensure_one()
        action = self.env.ref('chatroom_ai_autonomy.action_chatroom_ai_autonomy_exception', raise_if_not_found=False)
        if not action:
            return False
        result = action.read()[0]
        result['domain'] = [('state', 'in', ('open', 'in_progress'))]
        return result

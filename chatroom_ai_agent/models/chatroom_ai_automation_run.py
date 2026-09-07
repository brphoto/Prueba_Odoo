# -*- coding: utf-8 -*-
from odoo import _, fields, models


class ChatroomAiAutomationRun(models.Model):
    _name = 'chatroom.ai.automation.run'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Ejecución de automatización del agente IA'
    _order = 'execution_date desc, id desc'
    _rec_name = 'summary'

    automation_id = fields.Many2one(
        'chatroom.ai.automation', string='Automatización', required=True,
        ondelete='cascade', index=True)
    execution_date = fields.Datetime(
        string='Ejecutada el', required=True, default=fields.Datetime.now,
        index=True)
    execution_type = fields.Selection([
        ('manual', 'Manual'),
        ('automatic', 'Automática'),
    ], string='Origen', required=True, default='manual')
    state = fields.Selection([
        ('completed', 'Completada'),
        ('failed', 'Con incidencias'),
    ], string='Estado', required=True, default='completed')
    channels_scanned = fields.Integer(string='Canales revisados')
    tasks_created = fields.Integer(string='Tareas creadas')
    channels_skipped = fields.Integer(string='Canales omitidos')
    tasks_reused = fields.Integer(string='Tareas ya existentes')
    channels_failed = fields.Integer(string='Canales con incidencia')
    summary = fields.Char(string='Resumen', required=True)
    skip_details = fields.Text(string='Detalle de omitidos')
    error_details = fields.Text(string='Incidencias')
    task_ids = fields.Many2many(
        'chatroom.ai.task', 'chatroom_ai_automation_run_task_rel',
        'run_id', 'task_id', string='Tareas generadas', readonly=True)

    def action_view_tasks(self):
        self.ensure_one()
        action = self.env.ref('chatroom_ai_agent.action_chatroom_ai_task').read()[0]
        action.update({
            'name': _('Tareas de la ejecución'),
            'domain': [('id', 'in', self.task_ids.ids)],
            'context': {},
        })
        return action

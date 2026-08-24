# -*- coding: utf-8 -*-
from odoo import fields, models


class ChatroomAiAudit(models.Model):
    _name = 'chatroom.ai.audit'
    _description = 'Auditoría del agente IA de Chatroom'
    _order = 'create_date desc, id desc'

    name = fields.Char(string='Operación', required=True, index=True)
    task_id = fields.Many2one('chatroom.ai.task', string='Tarea', ondelete='cascade', index=True)
    action_id = fields.Many2one('chatroom.ai.task.action', string='Acción', ondelete='set null')
    tool_id = fields.Many2one('chatroom.ai.tool', string='Herramienta', ondelete='set null')
    user_id = fields.Many2one('res.users', string='Usuario', default=lambda self: self.env.user, index=True)
    state = fields.Selection([
        ('started', 'Iniciada'), ('done', 'Completada'), ('error', 'Error'),
        ('blocked', 'Bloqueada'),
    ], string='Estado', required=True, default='started', index=True)
    input_json = fields.Text(string='Entrada técnica', readonly=True)
    output_json = fields.Text(string='Salida técnica', readonly=True)
    message = fields.Text(string='Detalle', readonly=True)
    duration_ms = fields.Integer(string='Duración (ms)', readonly=True)

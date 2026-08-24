# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    chatroom_ai_agent_enabled = fields.Boolean(
        string='Activar automatizaciones del agente IA',
        config_parameter='chatroom_ai_agent.enabled',
        help='Permite que las automatizaciones creen y ejecuten tareas según sus reglas.',
    )
    chatroom_ai_agent_require_approval = fields.Boolean(
        string='Requerir aprobación para acciones sensibles', default=True,
        config_parameter='chatroom_ai_agent.require_approval',
        help='Las acciones que cambian datos o envían mensajes siempre conservan su aprobación propia.',
    )
    chatroom_ai_agent_mode = fields.Selection([
        ('supervised', 'Supervisado: requiere aprobacion'),
        ('automatic', 'Automatico: ejecuta tareas autorizadas'),
        ('simulation', 'Simulacion: solo prepara planes'),
    ], string='Modo de operacion del agente', default='supervised',
        config_parameter='chatroom_ai_agent.mode',
        help='El modo supervisado es el recomendado. El automatico no elimina las aprobaciones propias de cobros y envios.')
    chatroom_ai_agent_max_tasks = fields.Integer(
        string='Máximo de tareas por ciclo', default=20,
        config_parameter='chatroom_ai_agent.max_tasks',
    )
    chatroom_ai_agent_max_actions = fields.Integer(
        string='Maximo de acciones por tarea', default=8,
        config_parameter='chatroom_ai_agent.max_actions',
    )

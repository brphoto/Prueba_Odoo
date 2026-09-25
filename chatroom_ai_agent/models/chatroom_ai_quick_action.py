# -*- coding: utf-8 -*-
from odoo import fields, models


class ChatroomAiQuickAction(models.Model):
    _inherit = 'chatroom.ai.quick.action'

    output_mode = fields.Selection(
        selection_add=[('agent_task', 'Tarea del agente (con aprobación)')],
        ondelete={'agent_task': 'set default'})
    agent_task_type = fields.Selection([
        ('orchestrate', 'Analizar conversación completa'),
        ('qualify_lead', 'Calificar oportunidad'),
        ('prepare_reply', 'Preparar respuesta'),
        ('followup', 'Preparar seguimiento'),
        ('collect_payment', 'Preparar cobranza'),
        ('sales_conversion', 'Convertir conversación en venta'),
    ], string='Tipo de tarea del agente', default='orchestrate',
        help='Qué prepara el agente. Las acciones sensibles (crear oportunidad, '
             'cotización, link de pago...) quedan esperando aprobación.')

# -*- coding: utf-8 -*-
from odoo import fields, models


class ChatroomAiAutomation(models.Model):
    _inherit = 'chatroom.ai.automation'

    template_id = fields.Many2one(
        'chatroom.ai.message.template', string='Plantilla personalizada',
        domain="[('company_id', '=', company_id), ('active', '=', True)]",
        help='Se incorpora al contexto de la tarea cuando se ejecuta la automatización.')

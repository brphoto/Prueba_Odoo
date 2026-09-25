# -*- coding: utf-8 -*-
from odoo import fields, models


class ChatroomAiHandoffRule(models.Model):
    _inherit = 'chatroom.ai.handoff.rule'

    trigger = fields.Selection(selection_add=[('playbook', 'Se completó un guion')],
                               ondelete={'playbook': 'cascade'})

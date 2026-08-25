# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ChatroomMessage(models.Model):
    _inherit = 'chatroom.message'

    @api.model_create_multi
    def create(self, vals_list):
        messages = super().create(vals_list)
        enabled = self.env['ir.config_parameter'].sudo().get_param(
            'chatroom_ai_agent.event_orchestration', 'False') == 'True'
        if not enabled or 'chatroom.ai.automation' not in self.env:
            return messages
        automation_model = self.env['chatroom.ai.automation'].sudo()
        automations = automation_model.search([
            ('active', '=', True), ('trigger', '=', 'open_conversation'),
        ], order='sequence, id')
        if not automations:
            return messages
        tasks = self.env['chatroom.ai.task'].sudo()
        for message in messages.filtered(lambda item: item.direction == 'inbound' and item.channel_id):
            channel = message.channel_id
            if channel.ai_paused:
                continue
            for automation in automations[:1]:
                duplicate = tasks.search_count([
                    ('channel_id', '=', channel.id),
                    ('automation_id', '=', automation.id),
                    ('state', 'in', ('draft', 'awaiting_approval', 'planned', 'running')),
                ])
                if not duplicate:
                    tasks.create_from_channel(
                        channel, automation.task_type or 'followup',
                        automation.instruction or automation.name,
                        automation.approval_required,
                        automation=automation)
        return messages

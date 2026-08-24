# -*- coding: utf-8 -*-
from odoo import _, models


class ChatroomChannel(models.Model):
    _inherit = 'chatroom.channel'

    def get_ai_agent_data(self):
        self.ensure_one()
        can_use = self.env.user.has_group('chatroom_ai_agent.group_chatroom_ai_agent_user')
        if not can_use:
            return {'can_use': False, 'task': False}
        task = self.env['chatroom.ai.task'].search([
            ('channel_id', '=', self.id),
            ('state', '!=', 'cancelled'),
        ], order='create_date desc, id desc', limit=1)
        return {
            'can_use': True,
            'task': {
                'id': task.id,
                'name': task.name,
                'state': task.state,
                'state_label': dict(task._fields['state'].selection).get(task.state, task.state),
                'action_count': len(task.action_ids),
                'result_summary': task.result_summary or '',
            } if task else False,
        }

    def action_ai_agent_create_task(self):
        self.ensure_one()
        task = self.env['chatroom.ai.task'].create_from_channel(self)
        task.action_plan()
        return {
            'type': 'ir.actions.act_window', 'name': _('Plan IA'),
            'res_model': 'chatroom.ai.task', 'res_id': task.id,
            'views': [(False, 'form')], 'target': 'new',
        }

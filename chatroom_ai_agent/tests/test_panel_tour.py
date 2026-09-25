# -*- coding: utf-8 -*-
"""Panel compacto del Agente IA en un navegador real."""
from odoo.fields import Datetime
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestPanelTour(HttpCase):

    def test_agent_panel_tour(self):
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('chatroom_whatsapp.ai_enabled', 'False')
        icp.set_param('chatroom_ai_agent.event_orchestration', 'False')
        admin = self.env.ref('base.user_admin')
        admin.chatroom_ai_agent_panel = 'auto'
        partner = self.env['res.partner'].create({'name': 'TOUR AGENTE'})
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp', 'external_id': '573001119991',
            'partner_id': partner.id, 'assigned_user_id': admin.id,
            'last_message_date': Datetime.now(),
        })
        self.env['chatroom.message'].create({
            'channel_id': channel.id, 'direction': 'inbound', 'state': 'read',
            'body': 'Quiero comprar dos sillas', 'date': Datetime.now(),
        })
        task = self.env['chatroom.ai.task'].create_from_channel(
            channel, task_type='classify_customer', prompt='Tarea del tour')
        task.action_plan()
        self.assertEqual(task.state, 'awaiting_approval')
        self.env.flush_all()
        self.start_tour(
            '/odoo/action-chatroom_whatsapp.action_chatroom_app',
            'chatroom_ai_agent_panel_tour', login='admin')
        self.assertEqual(admin.chatroom_ai_agent_panel, 'hidden')

# -*- coding: utf-8 -*-
"""Panel compacto del agente, preferencia por usuario y acciones rápidas
que preparan tareas del agente."""
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestPanelCompacto(TransactionCase):

    def setUp(self):
        super().setUp()
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('chatroom_whatsapp.ai_enabled', 'False')
        icp.set_param('chatroom_ai_agent.event_orchestration', 'False')
        self.channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp', 'external_id': 'panel-compacto-001',
        })
        self.other_channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp', 'external_id': 'panel-compacto-002',
        })

    def test_quick_action_can_prepare_an_agent_task(self):
        action = self.env.ref('chatroom_ai_agent.quick_action_agent_sale')
        self.assertIn(action.id, [a['id'] for a in self.channel.get_ai_quick_actions()])
        result = self.channel.action_ai_run_quick_action(action.id)
        self.assertEqual(result['mode'], 'agent_task')
        task = self.env['chatroom.ai.task'].browse(result['task_id'])
        self.assertEqual(task.channel_id, self.channel)
        self.assertEqual(task.task_type, 'sales_conversion')
        self.assertTrue(task.approval_required)
        self.assertEqual(result['action']['res_id'], task.id)
        self.assertEqual(action.use_count, 1)

    def test_open_task_only_from_its_own_conversation(self):
        task = self.env['chatroom.ai.task'].create_from_channel(
            self.other_channel, task_type='classify_customer', prompt='QA')
        with self.assertRaises(UserError):
            self.channel.action_ai_agent_open_task(task.id)
        action = self.other_channel.action_ai_agent_open_task(task.id)
        self.assertEqual(action['res_id'], task.id)
        self.assertEqual(action['target'], 'new')

    def test_panel_preference_is_per_user_and_self_editable(self):
        agent = new_test_user(
            self.env, login='agente_panel_qa',
            groups='chatroom_whatsapp.group_chatroom_user,chatroom_ai_agent.group_chatroom_ai_agent_user')
        self.assertEqual(agent.chatroom_ai_agent_panel, 'auto')
        self.env['res.users'].with_user(agent).set_chatroom_ai_agent_panel('hidden')
        self.assertEqual(agent.chatroom_ai_agent_panel, 'hidden')
        agent.with_user(agent).write({'chatroom_ai_agent_panel': 'open'})
        self.assertEqual(agent.chatroom_ai_agent_panel, 'open')
        with self.assertRaises(UserError):
            self.env['res.users'].with_user(agent).set_chatroom_ai_agent_panel('invalido')

    def test_counters_only_count_what_the_user_can_see(self):
        agent = new_test_user(
            self.env, login='agente_contadores_qa',
            groups='chatroom_whatsapp.group_chatroom_user,chatroom_ai_agent.group_chatroom_ai_agent_user')
        self.channel.assigned_user_id = agent
        mine = self.env['chatroom.ai.task'].create_from_channel(
            self.channel, task_type='classify_customer', prompt='Mía')
        mine.action_plan()
        other = self.env['chatroom.ai.task'].create_from_channel(
            self.other_channel, task_type='classify_customer', prompt='Ajena')
        other.action_plan()
        data = self.channel.with_user(agent).get_ai_agent_data()
        visible = self.env['chatroom.ai.task'].with_user(agent).search_count([
            ('state', '=', 'awaiting_approval')])
        self.assertEqual(data['approval_count'], visible)
        self.assertEqual(data['panel_pref'], 'auto')
        self.assertEqual(data['channel_pending_count'], 1)

    def test_only_server_code_can_authorize_a_task_by_policy(self):
        manager = new_test_user(
            self.env, login='admin_agente_politica_qa',
            groups='chatroom_whatsapp.group_chatroom_manager,chatroom_ai_agent.group_chatroom_ai_agent_manager')
        task = self.env['chatroom.ai.task'].create_from_channel(
            self.channel, task_type='classify_customer', prompt='QA política')
        with self.assertRaises(AccessError):
            task.with_user(manager).with_context(chatroom_ai_policy_release=True).write(
                {'policy_approved': True})
        task.sudo().write({'policy_approved': True})
        self.assertTrue(task.policy_approved)

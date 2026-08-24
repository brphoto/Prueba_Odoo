# -*- coding: utf-8 -*-
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestChatroomAiAgent(TransactionCase):

    def setUp(self):
        super().setUp()
        self.channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp',
            'external_id': 'ai-agent-test-001',
        })

    def test_task_generates_approved_plan_and_completes(self):
        task = self.env['chatroom.ai.task'].create_from_channel(
            self.channel, task_type='classify_customer',
            prompt='Clasifica este cliente para el siguiente seguimiento.',
        )
        task.action_plan()
        self.assertEqual(task.state, 'awaiting_approval')
        self.assertEqual(task.action_ids.mapped('key'), ['classify_customer'])
        task.action_approve()
        task.action_run()
        self.assertEqual(task.state, 'done')
        self.assertTrue(task.output_json)
        self.assertTrue(task.audit_ids)

    def test_memory_is_deduplicated(self):
        memory_model = self.env['chatroom.ai.memory']
        first = memory_model.remember('Cliente prefiere contacto por WhatsApp', channel=self.channel, memory_type='preference')
        second = memory_model.remember('Cliente prefiere contacto por WhatsApp', channel=self.channel, memory_type='preference')
        self.assertEqual(first, second)
        self.assertEqual(memory_model.search_count([('channel_id', '=', self.channel.id)]), 1)

    def test_sales_conversion_plan_is_approval_protected(self):
        task = self.env['chatroom.ai.task'].create_from_channel(
            self.channel, task_type='sales_conversion',
            prompt='Convierte esta conversación en una oportunidad y cotización.',
        )
        task.action_plan()
        self.assertEqual(task.state, 'awaiting_approval')
        self.assertEqual(
            task.action_ids.mapped('key'),
            ['search_catalog', 'classify_intent', 'create_lead', 'create_quotation', 'create_activity'],
        )
        self.assertFalse(task.action_ids.filtered(lambda action: action.key == 'search_catalog').requires_approval)
        self.assertTrue(all(task.action_ids.filtered(lambda action: action.key not in ('classify_intent', 'search_catalog')).mapped('requires_approval')))

    def test_automation_reports_execution_result(self):
        automation = self.env['chatroom.ai.automation'].create({
            'name': 'Prueba de seguimiento comercial',
            'trigger': 'open_opportunity',
            'task_type': 'followup',
            'approval_required': True,
            'max_tasks': 1,
        })
        notification = automation.action_run_now()
        self.assertEqual(notification.get('tag'), 'display_notification')
        self.assertGreaterEqual(automation.last_run_count, 0)
        self.assertTrue(automation.last_run)
        self.assertFalse(automation.last_error)

    def test_commercial_automation_triggers_are_available(self):
        automation_model = self.env['chatroom.ai.automation']
        for trigger in ('open_opportunity', 'pending_quote', 'pending_activity'):
            automation = automation_model.create({
                'name': 'Prueba %s' % trigger,
                'trigger': trigger,
                'task_type': 'followup',
                'approval_required': True,
                'max_tasks': 1,
            })
            notification = automation.action_run_now()
            self.assertEqual(notification.get('tag'), 'display_notification')
            self.assertTrue(automation.last_run)

    def test_bulk_controls_keep_state_gates(self):
        planned = self.env['chatroom.ai.task'].create({
            'name': 'Tarea planificada de prueba', 'task_type': 'orchestrate', 'state': 'planned',
            'approval_required': False, 'channel_id': self.channel.id,
        })
        failed = self.env['chatroom.ai.task'].create({
            'name': 'Tarea fallida de prueba', 'task_type': 'orchestrate', 'state': 'failed',
            'approval_required': False, 'channel_id': self.channel.id,
        })
        run_notification = (planned | failed).action_run_selected()
        self.assertEqual(run_notification.get('tag'), 'display_notification')
        self.assertEqual(planned.state, 'done')
        retry_notification = (planned | failed).action_retry_selected()
        self.assertEqual(retry_notification.get('tag'), 'display_notification')
        self.assertEqual(failed.state, 'planned')

    def test_agent_menu_is_exposed_from_chatroom_root(self):
        menu = self.env.ref('chatroom_ai_agent.menu_chatroom_ai_agent')
        self.assertEqual(menu.parent_id, self.env.ref('chatroom_whatsapp.menu_chatroom_root'))
        self.assertTrue(self.env.ref('chatroom_ai_agent.menu_chatroom_ai_tasks').action)
        self.assertTrue(self.env.ref('chatroom_ai_agent.menu_chatroom_ai_control').action)
        self.assertTrue(self.env.ref('chatroom_ai_agent.menu_chatroom_ai_approvals').action)
        self.assertTrue(self.env.ref('chatroom_ai_agent.menu_chatroom_ai_failed').action)

    def test_contact_panel_actions_are_dialog_safe(self):
        action_methods = {
            'action_view_leads': 'crm.lead',
            'action_view_sale_orders': 'sale.order',
            'action_view_purchases': 'purchase.order',
            'action_view_invoices': 'account.move',
            'action_view_tasks': 'project.task',
        }
        for method_name, model_name in action_methods.items():
            if model_name not in self.env:
                continue
            action = getattr(self.channel, method_name)()
            self.assertEqual(action.get('type'), 'ir.actions.act_window')
            self.assertEqual(action.get('target'), 'new')
            self.assertTrue(action.get('views'))
            self.assertIn((False, 'form'), action['views'])

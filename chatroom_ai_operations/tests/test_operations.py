# -*- coding: utf-8 -*-
from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestChatroomAiOperations(TransactionCase):

    def test_dashboard_refresh_and_actions(self):
        dashboard = self.env['chatroom.operations.dashboard'].create({})
        dashboard._refresh_metrics()
        self.assertIsNotNone(dashboard.refreshed_at)
        self.assertEqual(dashboard.company_id, self.env.company)
        self.assertIsInstance(dashboard.active_conversations, int)
        self.assertEqual(dashboard.action_open_failed_payments()['target'], 'new')

    def test_playbook_safe_mode_creates_internal_notification(self):
        partner = self.env.ref('base.partner_root')
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp',
            'external_id': 'operations-test-%s' % partner.id,
            'partner_id': partner.id,
        })
        playbook = self.env['chatroom.operations.playbook'].create({
            'name': 'QA seguimiento',
            'trigger': 'manual',
            'test_channel_id': channel.id,
            'execution_mode': 'notify',
            'approval_required': True,
        })
        playbook._notify(channel, 'Aviso interno de prueba')
        self.assertTrue(self.env['chatroom.notification'].search_count([
            ('channel_id', '=', channel.id), ('message', '=', 'Aviso interno de prueba'),
        ]))
        action = playbook.action_run_now()
        self.assertEqual(action['type'], 'ir.actions.client')
        self.assertIn('1 canal(es)', playbook.last_result)

    def test_demo_generator_is_safe_and_idempotent(self):
        demo = self.env['chatroom.operations.demo'].create({})
        demo.action_generate()
        self.assertEqual(demo.scenario_count, 6)
        self.assertEqual(self.env['chatroom.operations.playbook'].search_count([
            ('name', 'like', 'DEMO QA - Aviso%'), ('active', '=', False),
        ]), 3)

    def test_daily_metrics_are_refreshable_and_unique(self):
        metrics = self.env['chatroom.operations.metric']
        first = metrics.collect_for_date()
        second = metrics.collect_for_date()
        self.assertEqual(first, second)
        self.assertEqual(first.date, fields.Date.context_today(self))
        self.assertEqual(first.company_id, self.env.company)
        self.assertGreaterEqual(first.conversation_count, 0)
        self.assertGreaterEqual(first.ai_tokens, 0)
        self.assertGreaterEqual(first.quotation_count, 0)
        self.assertGreaterEqual(first.confirmed_orders, 0)
        self.assertGreaterEqual(first.invoice_count, 0)
        self.assertGreaterEqual(first.new_customers, 0)

    def test_dashboard_can_refresh_persistent_metrics(self):
        dashboard = self.env['chatroom.operations.dashboard'].create({})
        action = dashboard.action_collect_metrics()
        self.assertEqual(action['tag'], 'display_notification')

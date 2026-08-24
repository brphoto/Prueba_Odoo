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

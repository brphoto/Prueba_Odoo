# -*- coding: utf-8 -*-
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestChatroomAiKnowledge(TransactionCase):

    def test_preview_reopens_wizard_with_results(self):
        wizard = self.env['chatroom.ai.knowledge.test'].create({
            'question': 'Que productos y precios puede consultar la IA?',
        })
        action = wizard.action_preview()
        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(action['res_model'], 'chatroom.ai.knowledge.test')
        self.assertEqual(action['res_id'], wizard.id)
        self.assertGreaterEqual(wizard.estimated_input_tokens, 0)

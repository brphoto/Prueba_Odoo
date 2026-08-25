# -*- coding: utf-8 -*-
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestChatroomAiAutonomySimulator(TransactionCase):

    def test_simulation_reopens_with_decision_and_traceability(self):
        self.env['chatroom.ai.autonomy.policy'].search([]).write({'active': False})
        policy = self.env['chatroom.ai.autonomy.policy'].create({
            'name': 'Prueba segura',
            'mode': 'approval',
            'allow_reply': True,
        })
        simulator = self.env['chatroom.ai.autonomy.simulator'].create({
            'query': 'Que productos tienen disponibles?',
            'action_key': 'reply',
        })
        action = simulator.action_simulate()
        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(action['res_model'], 'chatroom.ai.autonomy.simulator')
        self.assertEqual(simulator.request_id.policy_id, policy)
        self.assertTrue(simulator.decision)
        self.assertTrue(simulator.simulation_message)

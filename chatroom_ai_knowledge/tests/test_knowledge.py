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

    def test_composer_creates_and_organizes_natural_knowledge(self):
        composer = self.env['chatroom.ai.knowledge.composer'].create({
            'name': 'QA conocimiento comercial',
            'category': 'sales',
            'knowledge_format': 'policy',
            'source_text': 'Somos implementadores de Odoo.\nTarifa: USD 20 por hora.\nPregunta: ¿Qué necesitamos para cotizar?\nAlcance, usuarios y fecha objetivo.',
        })
        action = composer.action_create()
        manual = self.env['ai.knowledge.base'].browse(action['res_id'])
        self.assertEqual(manual.state, 'indexed')
        self.assertEqual(manual.organization_state, 'organized')
        self.assertIn('USD 20', manual.organized_text)
        self.assertIn('PREGUNTAS FRECUENTES', manual.organized_text)

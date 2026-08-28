# -*- coding: utf-8 -*-
from unittest.mock import patch

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

    def test_composer_accepts_pdf_source(self):
        # The source validation is exercised with a minimal valid PDF payload;
        # the actual extraction is covered by the shared indexer tests.
        pdf = (
            b'%PDF-1.4\n1 0 obj<<>>endobj\n'
            b'trailer<<>>\n%%EOF'
        )
        composer = self.env['chatroom.ai.knowledge.composer'].create({
            'name': 'QA fuente PDF', 'source_type': 'pdf',
            'pdf_file': __import__('base64').b64encode(pdf),
            'pdf_filename': 'qa.pdf',
        })
        self.assertEqual(composer.source_type, 'pdf')

    def test_knowledge_analysis_has_local_zero_token_fallback(self):
        manual = self.env['ai.knowledge.base'].create({
            'name': 'QA cerebro local', 'source_type': 'text',
            'source_text': 'Somos implementadores de Odoo. Tarifa: USD 20 por hora.',
        })
        manual.action_index()
        with patch.object(type(manual), '_analysis_channel', return_value=False):
            manual.action_analyze_with_ai()
        self.assertIn(manual.analysis_state, ('needs_review', 'error'))
        self.assertTrue(manual.analysis_summary)
        self.assertIn(manual.analysis_source, ('local', 'provider', 'local_fallback'))
        self.assertEqual(manual.analysis_input_tokens, 0)

    def test_knowledge_answer_can_be_approved_or_corrected(self):
        wizard = self.env['chatroom.ai.knowledge.test'].create({
            'question': '¿Qué información puede utilizar la IA?',
            'answer': 'Respuesta de prueba',
        })
        wizard.action_approve_answer()
        self.assertEqual(wizard.answer_review_state, 'approved')
        wizard.answer_correction = 'Respuesta corregida y aprobada por el usuario.'
        wizard.action_save_correction()
        self.assertEqual(wizard.answer_review_state, 'corrected')
        self.assertEqual(wizard.answer, wizard.answer_correction)

    def test_knowledge_test_provider_path_keeps_translation_context_valid(self):
        manual = self.env['ai.knowledge.base'].create({
            'name': 'QA prueba proveedor', 'source_type': 'text',
            'source_text': 'Somos implementadores de Odoo y ofrecemos desarrollo personalizado.',
            'publication_state': 'published',
        })
        manual.action_index()
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp', 'external_id': 'knowledge-test-provider-001',
        })
        wizard = self.env['chatroom.ai.knowledge.test'].create({
            'question': '¿Qué servicios ofrecen?', 'channel_id': channel.id,
        })
        with patch.object(type(wizard), '_provider_channel', return_value=channel), \
                patch.object(type(channel), '_ai_get_credentials', return_value=(True, 'test-key', 'test-model')), \
                patch.object(type(channel), '_ai_chat_completion', return_value='{"answer":"Ofrecemos desarrollo personalizado.", "confidence":0.9, "used_sources":["QA prueba proveedor"]}'):
            wizard.action_ask_ai()
        self.assertEqual(wizard.answer_source, 'provider')
        self.assertEqual(wizard.answer, 'Ofrecemos desarrollo personalizado.')
        self.assertEqual(wizard.answer_model, 'test-model')

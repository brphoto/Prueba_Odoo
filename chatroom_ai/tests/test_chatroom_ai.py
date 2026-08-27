# -*- coding: utf-8 -*-
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestChatroomAiSuggestion(TransactionCase):

    def setUp(self):
        super().setUp()
        self.channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp', 'external_id': 'qa-ai-controlled',
        })

    def test_suggestion_must_be_approved_before_sending(self):
        suggestion = self.env['chatroom.ai.suggestion'].create_from_channel(
            self.channel, 'Respuesta preparada para revisión')
        self.assertEqual(suggestion.state, 'draft')
        with self.assertRaises(Exception):
            suggestion.action_send()
        suggestion.action_approve()
        self.assertEqual(suggestion.state, 'approved')
        self.assertTrue(suggestion.approved_by)

    def test_suggestion_can_be_edited_and_rejected(self):
        suggestion = self.env['chatroom.ai.suggestion'].create_from_channel(
            self.channel, 'Texto inicial')
        suggestion.suggested_text = 'Texto revisado por el agente'
        suggestion.action_reject()
        self.assertEqual(suggestion.state, 'rejected')
        self.assertEqual(suggestion.suggested_text, 'Texto revisado por el agente')

    def test_panel_flow_prepares_and_approves_without_network(self):
        data = self.channel.get_ai_assistant_data()
        self.assertIn('provider_ready', data)
        with patch.object(type(self.channel), '_ai_chat_completion',
                          return_value='Respuesta simulada del panel'):
            prepared = self.channel.action_ai_prepare_suggestion()
        self.assertEqual(prepared['state'], 'draft')
        approved = self.channel.action_ai_approve_suggestion(prepared['id'])
        self.assertEqual(approved['suggestion']['state'], 'approved')

    def test_panel_draft_can_be_edited_or_discarded(self):
        suggestion = self.env['chatroom.ai.suggestion'].create_from_channel(
            self.channel, 'Texto que debe revisarse')
        data = self.channel.action_ai_update_suggestion(
            suggestion.id, 'Texto corregido por el agente')
        self.assertEqual(data['suggestion']['text'], 'Texto corregido por el agente')
        discarded = self.channel.action_ai_discard_suggestion(suggestion.id)
        self.assertFalse(discarded['suggestion'])

    def test_summary_is_internal_and_never_creates_sendable_suggestion(self):
        self.channel.ai_suggested_reply = 'Respuesta anterior que no debe mezclarse'
        with patch.object(type(self.channel), '_ai_chat_completion',
                          return_value='El cliente solicita una cotización y espera confirmación del alcance.'):
            summary = self.channel.action_ai_prepare_summary()
        self.assertIn('cotización', summary)
        self.assertEqual(self.channel.ai_summary, summary)
        self.assertEqual(self.channel.ai_suggested_reply,
                         'Respuesta anterior que no debe mezclarse')
        self.assertFalse(self.env['chatroom.ai.suggestion'].search([
            ('channel_id', '=', self.channel.id),
        ]))

    def test_intent_analysis_and_next_action_are_structured_and_supervised(self):
        with patch.object(type(self.channel), '_ai_chat_completion',
                          return_value='{"intent":"venta"}'):
            intent = self.channel.action_ai_classify_intent()
        self.assertEqual(intent, 'venta')
        with patch.object(type(self.channel), '_ai_chat_completion',
                          return_value='{"intent":"soporte","sentiment":"negative","urgency":"high"}'):
            self.channel.action_ai_analyze()
        self.assertEqual(self.channel.ai_intent, 'soporte')
        self.assertEqual(self.channel.ai_sentiment, 'negative')
        self.assertEqual(self.channel.ai_urgency, 'high')
        with patch.object(type(self.channel), '_ai_chat_completion',
                          return_value='Confirmar el alcance y enviar la cotización al cliente.'):
            self.channel.action_ai_next_action()
        self.assertIn('cotización', self.channel.ai_next_action)

    def test_invalid_ai_analysis_falls_back_to_safe_values(self):
        with patch.object(type(self.channel), '_ai_chat_completion',
                          return_value='No puedo devolver JSON en este momento'):
            self.channel.action_ai_analyze()
        self.assertEqual(self.channel.ai_intent, 'otro')
        self.assertEqual(self.channel.ai_sentiment, 'neutral')
        self.assertEqual(self.channel.ai_urgency, 'normal')

    def test_suggestion_feedback_is_a_quality_rating_not_customer_rating(self):
        suggestion = self.env['chatroom.ai.suggestion'].create_from_channel(
            self.channel, 'Respuesta que el agente puede revisar')
        suggestion.action_approve()
        data = self.channel.action_ai_feedback_suggestion(suggestion.id, 'helpful')
        self.assertEqual(data['suggestion']['feedback_state'], 'helpful')
        self.assertEqual(suggestion.feedback_by, self.env.user)

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

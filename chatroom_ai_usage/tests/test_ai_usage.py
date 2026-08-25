# -*- coding: utf-8 -*-
from unittest.mock import Mock, patch

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestChatroomAiUsage(TransactionCase):

    def test_model_catalog_classifies_chat_models(self):
        model = self.env['chatroom.ai.provider.model']
        self.assertTrue(model._looks_like_chat_model('gpt-4o-mini'))
        self.assertTrue(model._looks_like_chat_model('o3-mini'))
        self.assertFalse(model._looks_like_chat_model('text-embedding-3-small'))
        self.assertFalse(model._looks_like_chat_model('gpt-realtime'))
        self.assertTrue(model._is_recommended('gpt-4o-mini'))

    def test_selected_model_overrides_manual_fallback(self):
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('chatroom_whatsapp.ai_enabled', 'True')
        icp.set_param('chatroom_whatsapp.ai_provider_url', 'https://api.openai.com/v1/chat/completions')
        icp.set_param('chatroom_whatsapp.ai_api_key', 'test-key')
        icp.set_param('chatroom_whatsapp.ai_model', 'gpt-4o-mini')
        selected = self.env['chatroom.ai.provider.model'].create({
            'name': 'test-selector-model', 'model_id': 'test-selector-model',
            'provider': 'openai', 'supports_chat': True, 'active': True,
        })
        icp.set_param('chatroom_whatsapp.ai_model_id', str(selected.id))
        channel = self.env['chatroom.channel'].create({'channel_type': 'whatsapp', 'external_id': 'usage-test-001'})
        self.assertEqual(channel._ai_get_credentials()[2], 'test-selector-model')

    def test_conversation_panel_exposes_safe_model_catalog(self):
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('chatroom_whatsapp.ai_enabled', 'True')
        icp.set_param('chatroom_whatsapp.ai_provider_url', 'https://api.openai.com/v1/chat/completions')
        icp.set_param('chatroom_whatsapp.ai_api_key', 'test-key')
        selected = self.env['chatroom.ai.provider.model'].create({
            'name': 'panel-visible-model', 'model_id': 'panel-visible-model',
            'provider': 'openai', 'supports_chat': True, 'active': True,
            'recommended': True,
        })
        icp.set_param('chatroom_whatsapp.ai_model_reply_id', str(selected.id))
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp', 'external_id': 'usage-test-panel',
        })
        data = channel.get_ai_assistant_data()
        self.assertEqual(data['selected_model_id'], selected.id)
        self.assertIn('panel-visible-model', [item['model_id'] for item in data['model_options']])
        self.assertNotIn('api_key', data)
        self.assertNotIn('provider_url', data)

    def test_explicit_panel_model_is_validated_and_used(self):
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('chatroom_whatsapp.ai_enabled', 'True')
        icp.set_param('chatroom_whatsapp.ai_provider_url', 'https://api.openai.com/v1/chat/completions')
        icp.set_param('chatroom_whatsapp.ai_api_key', 'test-key')
        selected = self.env['chatroom.ai.provider.model'].create({
            'name': 'panel-explicit-model', 'model_id': 'panel-explicit-model',
            'provider': 'openai', 'supports_chat': True, 'active': True,
        })
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp', 'external_id': 'usage-test-explicit',
        })
        self.assertEqual(
            channel._ai_get_credentials(task_type='reply', model_id=selected.id)[2],
            'panel-explicit-model',
        )

    def test_local_usage_event_totals(self):
        event = self.env['chatroom.ai.usage.event'].create({
            'model': 'gpt-4o-mini', 'input_tokens': 10,
            'output_tokens': 7, 'total_tokens': 17,
        })
        self.assertEqual(event.total_tokens, event.input_tokens + event.output_tokens)

    def test_budget_alert_thresholds(self):
        self.env['ir.config_parameter'].sudo().set_param('chatroom_whatsapp.ai_monthly_budget', '10')
        values = self.env['chatroom.ai.usage.snapshot']._budget_values(8.5)
        self.assertEqual(values['budget_state'], 'warning')
        self.assertEqual(values['budget_remaining'], 1.5)

    def test_task_profile_and_fallback_models_are_ordered(self):
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('chatroom_whatsapp.ai_enabled', 'True')
        icp.set_param('chatroom_whatsapp.ai_provider_url', 'https://api.openai.com/v1/chat/completions')
        icp.set_param('chatroom_whatsapp.ai_api_key', 'test-key')
        primary = self.env['chatroom.ai.provider.model'].create({
            'name': 'profile-primary', 'model_id': 'profile-primary',
            'provider': 'openai', 'supports_chat': True, 'active': True,
        })
        backup = self.env['chatroom.ai.provider.model'].create({
            'name': 'profile-backup', 'model_id': 'profile-backup',
            'provider': 'openai', 'supports_chat': True, 'active': True,
        })
        icp.set_param('chatroom_whatsapp.ai_model_reply_id', str(primary.id))
        icp.set_param('chatroom_whatsapp.ai_fallback_model_id', str(backup.id))
        channel = self.env['chatroom.channel'].create({'channel_type': 'whatsapp', 'external_id': 'usage-test-002'})
        self.assertEqual([item[2] for item in channel._ai_model_candidates('reply')], ['profile-primary', 'profile-backup'])

    def test_memory_context_expires_and_is_retrievable(self):
        if 'chatroom.ai.memory' not in self.env:
            self.skipTest('Agente IA no instalado')
        partner = self.env['res.partner'].create({'name': 'Cliente contexto IA'})
        memory = self.env['chatroom.ai.memory'].remember('Prefiere recibir cotizaciones por WhatsApp', partner=partner)
        self.assertIn('cotizaciones', self.env['chatroom.ai.memory'].get_context(partner=partner))
        memory.write({'expires_at': '2000-01-01 00:00:00'})
        self.assertNotIn('cotizaciones', self.env['chatroom.ai.memory'].get_context(partner=partner))

    def test_completion_uses_fallback_after_provider_error(self):
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('chatroom_whatsapp.ai_enabled', 'True')
        icp.set_param('chatroom_whatsapp.ai_provider_url', 'https://example.test/v1/chat/completions')
        icp.set_param('chatroom_whatsapp.ai_api_key', 'test-key')
        primary = self.env['chatroom.ai.provider.model'].create({
            'name': 'completion-primary', 'model_id': 'completion-primary',
            'provider': 'openai', 'supports_chat': True, 'active': True,
        })
        backup = self.env['chatroom.ai.provider.model'].create({
            'name': 'completion-backup', 'model_id': 'completion-backup',
            'provider': 'openai', 'supports_chat': True, 'active': True,
        })
        icp.set_param('chatroom_whatsapp.ai_model_id', str(primary.id))
        icp.set_param('chatroom_whatsapp.ai_fallback_model_id', str(backup.id))
        channel = self.env['chatroom.channel'].create({'channel_type': 'whatsapp', 'external_id': 'usage-test-003'})
        failed = Mock(status_code=503)
        success = Mock(status_code=200)
        success.json.return_value = {'choices': [{'message': {'content': 'Respuesta de respaldo'}}], 'usage': {}}
        with patch.object(type(channel), '_meta_request', side_effect=[failed, success]):
            self.assertEqual(channel._ai_chat_completion([{'role': 'user', 'content': 'Hola'}]), 'Respuesta de respaldo')
        self.assertEqual(self.env['chatroom.ai.usage.event'].search_count([('model', '=', 'completion-backup')]), 1)

# -*- coding: utf-8 -*-
from unittest.mock import Mock, patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestChatroomAiUsage(TransactionCase):

    def test_resource_limits_reject_expensive_context_configuration(self):
        with self.assertRaises(ValidationError):
            self.env['res.config.settings'].create({
                'chatroom_ai_history_messages': 31,
            })

    def test_resource_limits_allow_zero_daily_budgets(self):
        settings = self.env['res.config.settings'].create({
            'chatroom_ai_daily_token_limit': 0,
            'chatroom_ai_daily_request_limit': 0,
        })
        settings._check_ai_resource_limits()

    def test_model_catalog_classifies_chat_models(self):
        model = self.env['chatroom.ai.provider.model']
        self.assertTrue(model._looks_like_chat_model('gpt-4o-mini'))
        self.assertTrue(model._looks_like_chat_model('o3-mini'))
        self.assertFalse(model._looks_like_chat_model('text-embedding-3-small'))
        self.assertFalse(model._looks_like_chat_model('gpt-realtime'))
        self.assertTrue(model._is_recommended('gpt-4o-mini'))

    def test_provider_health_reports_missing_configuration_without_http(self):
        self.env['ir.config_parameter'].sudo().set_param('chatroom_whatsapp.ai_api_key', False)
        self.env['ir.config_parameter'].sudo().set_param('chatroom_whatsapp.ai_provider_url', False)
        model = self.env['chatroom.ai.provider.model'].create({
            'name': 'health-test', 'model_id': 'health-test',
            'provider': 'openai', 'supports_chat': True,
        })
        model.action_test_connection()
        self.assertEqual(model.health_state, 'error')
        self.assertIn('Falta', model.health_message)

    def test_sandbox_evaluates_expected_keywords_and_delivery_is_non_destructive(self):
        sandbox = self.env['chatroom.ai.sandbox'].create({
            'name': 'QA sandbox', 'scenario': 'product',
            'expected_keywords': 'producto, catálogo', 'prompt': 'Consulta',
        })
        state, note = sandbox._evaluate_output('Tenemos producto y catálogo disponibles.')
        self.assertEqual(state, 'passed')
        self.assertIn('todos', note)
        sandbox.write({'state': 'done', 'output': 'Mensaje de prueba'})
        sandbox.action_simulate_delivery()
        self.assertEqual(sandbox.delivery_state, 'simulated')
        self.assertIn('No se llamó a WhatsApp', sandbox.delivery_note)

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
        icp.set_param('chatroom_whatsapp.ai_model_reply_id', str(selected.id))
        self.assertIn('general', selected.usage_roles)
        self.assertIn('respuestas', selected.usage_roles)
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
        self.assertEqual(event.company_id, self.env.company)

    def test_budget_alert_thresholds(self):
        self.env['ir.config_parameter'].sudo().set_param('chatroom_whatsapp.ai_monthly_budget', '10')
        values = self.env['chatroom.ai.usage.snapshot']._budget_values(8.5)
        self.assertEqual(values['budget_state'], 'warning')
        self.assertEqual(values['budget_remaining'], 1.5)

    def test_local_refresh_creates_summary_from_registered_requests(self):
        self.env['chatroom.ai.usage.event'].create({
            'model': 'gpt-test-local', 'input_tokens': 4,
            'output_tokens': 3, 'total_tokens': 7,
        })
        snapshot = self.env['chatroom.ai.usage.snapshot'].action_refresh_local()
        self.assertEqual(snapshot.state, 'partial')
        self.assertEqual(snapshot.company_id, self.env.company)
        self.assertGreaterEqual(snapshot.request_count, 1)
        self.assertGreaterEqual(snapshot.total_tokens, 7)

    def test_local_refresh_ui_returns_notification(self):
        action = self.env['chatroom.ai.usage.snapshot'].action_refresh_local_ui()
        self.assertEqual(action['type'], 'ir.actions.client')
        self.assertEqual(action['tag'], 'display_notification')

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

    def test_daily_request_limit_blocks_external_completion(self):
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('chatroom_whatsapp.ai_enabled', 'True')
        icp.set_param('chatroom_whatsapp.ai_provider_url', 'https://example.test/v1/chat/completions')
        icp.set_param('chatroom_whatsapp.ai_api_key', 'test-key')
        icp.set_param('chatroom_whatsapp.ai_daily_request_limit', '1')
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp', 'external_id': 'usage-limit-test',
        })
        self.env['chatroom.ai.usage.event'].create({
            'company_id': self.env.company.id,
            'request_date': fields.Datetime.now(), 'total_tokens': 10,
        })
        with self.assertRaises(UserError):
            channel._ai_chat_completion([{'role': 'user', 'content': 'Hola'}])

    def test_funding_ledger_calculates_control_balance(self):
        funding = self.env['chatroom.ai.funding']
        funding.create({
            'name': 'Recarga de prueba', 'movement_type': 'credit',
            'amount': 10.0, 'currency': 'usd',
        })
        funding.create({
            'name': 'Ajuste de prueba', 'movement_type': 'debit',
            'amount': 1.0, 'currency': 'usd',
        })
        values = self.env['chatroom.ai.usage.snapshot']._financial_values(
            2.5, fields.Datetime.now())
        self.assertEqual(values['funding_total'], 10.0)
        self.assertEqual(values['funding_debits'], 1.0)
        self.assertEqual(values['funding_net'], 9.0)
        self.assertEqual(values['estimated_balance'], 6.5)
        self.assertEqual(values['financial_state'], 'available')

    def test_funding_ledger_rejects_non_positive_amount(self):
        with self.assertRaises(UserError):
            self.env['chatroom.ai.funding'].create({
                'name': 'Movimiento invalido', 'movement_type': 'credit',
                'amount': 0.0,
            })

    def test_official_cost_is_reconciled_with_registered_funds(self):
        self.env['chatroom.ai.funding'].create({
            'name': 'Fondo oficial de prueba', 'movement_type': 'credit',
            'amount': 10.0, 'currency': 'usd',
        })
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('chatroom_whatsapp.ai_admin_api_key', 'admin-test-key')
        usage_model = self.env['chatroom.ai.usage.snapshot']
        usage_payload = {'data': [{'results': [{
            'num_model_requests': 2, 'input_tokens': 100,
            'output_tokens': 40, 'model': 'gpt-test',
        }]}]}
        cost_payload = {'data': [{'results': [{
            'amount': {'value': 0.06, 'currency': 'usd'},
        }]}]}
        with patch.object(type(usage_model), '_fetch', side_effect=[usage_payload, cost_payload]):
            usage_model.action_refresh()
        snapshot = usage_model.search([], order='id desc', limit=1)
        self.assertEqual(snapshot.cost, 0.06)
        self.assertEqual(snapshot.currency, 'usd')
        self.assertEqual(snapshot.funding_net, 10.0)
        self.assertAlmostEqual(snapshot.estimated_balance, 9.94, places=5)
        self.assertEqual(snapshot.financial_state, 'available')

    def test_billing_link_opens_official_platform(self):
        action = self.env['chatroom.ai.usage.snapshot'].action_open_platform_billing()
        self.assertEqual(action['type'], 'ir.actions.act_url')
        self.assertIn('platform.openai.com/account/billing', action['url'])

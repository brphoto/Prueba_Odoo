# -*- coding: utf-8 -*-
import base64
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

    def test_sandbox_playground_supports_multi_turn_local_chat_without_tokens(self):
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp', 'external_id': 'sandbox-playground-001',
        })
        sandbox = self.env['chatroom.ai.sandbox'].create({
            'name': 'Laboratorio QA multi-turno', 'channel_id': channel.id,
            'execution_mode': 'local', 'prompt': 'Responde en español y no inventes información.',
        })
        sandbox.write({'draft_message': 'Hola'})
        action = sandbox.action_send_test_message()
        self.assertEqual(action['res_id'], sandbox.id)
        self.assertEqual(sandbox.conversation_line_ids.mapped('speaker'), ['customer', 'assistant'])
        self.assertEqual(sandbox.input_tokens, 0)
        sandbox.write({'draft_message': '¿Cuál es la tarifa por hora?'})
        sandbox.action_send_test_message()
        self.assertEqual(len(sandbox.conversation_line_ids), 4)
        self.assertEqual(sandbox.message_count, 4)
        self.assertIn('USD 20', sandbox.conversation_line_ids[-1].body)
        self.assertFalse(self.env['chatroom.ai.usage.event'].search_count([
            ('channel_id', '=', channel.id),
        ]))

    def test_sandbox_routes_quote_request_to_approved_agent_plan(self):
        if 'chatroom.ai.task' not in self.env:
            self.skipTest('Agente IA no instalado')
        partner = self.env['res.partner'].create({'name': 'Cliente laboratorio comercial'})
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp', 'external_id': 'sandbox-commercial-001',
            'partner_id': partner.id,
        })
        sandbox = self.env['chatroom.ai.sandbox'].create({
            'name': 'Prueba cotización y PDF', 'channel_id': channel.id,
            'execution_mode': 'local', 'prompt': 'Responde en español y explica el siguiente paso.',
        })
        sandbox.write({'draft_message': 'Necesito una cotización en PDF'})
        with patch.object(
            type(self.env['ir.actions.report']), '_render_qweb_pdf',
            return_value=(b'%PDF-1.4 route test', 'pdf'),
        ):
            sandbox.action_send_test_message()
        self.assertIn('cotización nativa', sandbox.output)
        action = sandbox.action_prepare_operational_task()
        task = self.env['chatroom.ai.task'].browse(action['res_id'])
        self.assertEqual(task.state, 'awaiting_approval')
        self.assertEqual(task.action_ids.mapped('key'), [
            'search_catalog', 'create_quotation', 'send_quotation_pdf'])

    def _create_sandbox_channel(self, external_id):
        partner = self.env['res.partner'].create({
            'name': 'Cliente prueba operativa',
            'email': 'cliente.prueba@example.test',
        })
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp', 'external_id': external_id,
            'partner_id': partner.id,
        })
        return partner, channel

    def test_sandbox_generates_native_draft_quote_and_pdf_attachment(self):
        partner, channel = self._create_sandbox_channel('sandbox-pdf-001')
        product = self.env['product.product'].create({
            'name': 'Servicio de prueba IA', 'type': 'service',
            'sale_ok': True, 'list_price': 20.0,
        })
        self.env['ir.config_parameter'].sudo().set_param(
            'chatroom_ai_agent.quote_product_id', str(product.id))
        sandbox = self.env['chatroom.ai.sandbox'].create({
            'name': 'Prueba PDF nativo', 'channel_id': channel.id,
            'execution_mode': 'local', 'prompt': 'Genera una cotización en PDF.',
        })
        with patch.object(
            type(self.env['ir.actions.report']), '_render_qweb_pdf',
            return_value=(b'%PDF-1.4 prueba', 'pdf'),
        ):
            action = sandbox.action_generate_test_quote_pdf()
        self.assertEqual(action['res_id'], sandbox.id)
        self.assertEqual(sandbox.test_quote_id.partner_id, partner)
        self.assertEqual(sandbox.test_quote_id.state, 'draft')
        self.assertEqual(sandbox.test_quote_id.order_line.product_id, product)
        self.assertEqual(len(sandbox.test_attachment_ids), 1)
        attachment = sandbox.test_attachment_ids
        self.assertEqual(attachment.mimetype, 'application/pdf')
        self.assertEqual(attachment.res_model, 'sale.order')
        self.assertEqual(attachment.res_id, sandbox.test_quote_id.id)
        self.assertEqual(base64.b64decode(attachment.datas), b'%PDF-1.4 prueba')
        self.assertEqual(sandbox.test_chat_message_id.channel_id, channel)
        self.assertEqual(sandbox.test_chat_message_id.message_type, 'document')
        self.assertEqual(sandbox.test_chat_message_id.attachment_ids, attachment)
        self.assertIn('No se confirmó', sandbox.operational_result)

    def test_sandbox_quote_uses_full_transcript_hours_product_and_native_price(self):
        _partner, channel = self._create_sandbox_channel('sandbox-context-quote-001')
        fallback = self.env['product.product'].create({
            'name': 'Producto fijo genérico', 'type': 'service',
            'sale_ok': True, 'list_price': 1.0,
        })
        requested = self.env['product.product'].create({
            'name': 'Implementación Odoo personalizada', 'type': 'service',
            'sale_ok': True, 'list_price': 20.0,
        })
        self.env['ir.config_parameter'].sudo().set_param(
            'chatroom_ai_agent.quote_product_id', str(fallback.id))
        sandbox = self.env['chatroom.ai.sandbox'].create({
            'name': 'Prueba contexto completo de cotización', 'channel_id': channel.id,
            'execution_mode': 'local', 'prompt': 'Responde en español.',
        })
        self.env['chatroom.ai.sandbox.message'].create([
            {'sandbox_id': sandbox.id, 'sequence': 10, 'speaker': 'customer',
             'body': 'Necesito implementar Odoo con personalización.'},
            {'sandbox_id': sandbox.id, 'sequence': 20, 'speaker': 'assistant',
             'body': 'La estimación inicial es de 3 horas de trabajo.'},
            {'sandbox_id': sandbox.id, 'sequence': 30, 'speaker': 'customer',
             'body': 'Perfecto, cotízame esas 3 horas en PDF.'},
        ])
        with patch.object(
            type(self.env['ir.actions.report']), '_render_qweb_pdf',
            return_value=(b'%PDF-1.4 contexto completo', 'pdf'),
        ):
            sandbox.action_generate_test_quote_pdf()
        order = sandbox.test_quote_id
        self.assertEqual(order.order_line.product_id, requested)
        self.assertEqual(order.order_line.product_uom_qty, 3.0)
        self.assertEqual(order.order_line.price_unit, 20.0)
        self.assertEqual(order.amount_untaxed, 60.0)
        self.assertIn('3 horas', order.note)
        self.assertIn('cantidad detectada: 3', sandbox.operational_result.lower())
        assistant = sandbox.test_chat_message_id
        self.assertIn('cantidad 3', assistant.body)
        self.assertIn('importe 60.00', assistant.body)

    def test_sandbox_creates_native_internal_activity_on_channel(self):
        partner, channel = self._create_sandbox_channel('sandbox-activity-001')
        sandbox = self.env['chatroom.ai.sandbox'].create({
            'name': 'Prueba actividad nativa', 'channel_id': channel.id,
            'execution_mode': 'local', 'prompt': 'Registrar seguimiento.',
        })
        sandbox.write({'draft_message': 'Crear una actividad interna de seguimiento para este cliente.'})
        action = sandbox.action_create_test_activity()
        self.assertEqual(action['res_id'], sandbox.id)
        self.assertEqual(len(sandbox.test_activity_ids), 1)
        activity = sandbox.test_activity_ids
        self.assertEqual(activity.res_model, 'chatroom.channel')
        self.assertEqual(activity.res_id, channel.id)
        self.assertEqual(activity.user_id, self.env.user)
        self.assertIn('seguimiento', activity.note.lower())
        self.assertIn('no se envió WhatsApp', sandbox.operational_result)
        self.assertEqual(channel.partner_id, partner)

    def test_sandbox_uses_upper_bound_for_knowledge_price_ranges(self):
        amounts = self.env['chatroom.ai.sandbox']._maximum_amounts_from_context(
            'Implementación estimada entre USD 200 y USD 300; tarifa USD 20 por hora.')
        self.assertEqual(max(amounts), 300.0)

    def test_sandbox_message_materializes_quote_pdf_and_activity_without_whatsapp(self):
        _partner, channel = self._create_sandbox_channel('sandbox-materialize-001')
        product = self.env['product.product'].create({
            'name': 'Implementación Odoo de prueba', 'type': 'service',
            'sale_ok': True, 'list_price': 20.0,
        })
        self.env['ir.config_parameter'].sudo().set_param(
            'chatroom_ai_agent.quote_product_id', str(product.id))
        sandbox = self.env['chatroom.ai.sandbox'].create({
            'name': 'Prueba punta a punta de documentos', 'channel_id': channel.id,
            'execution_mode': 'local', 'prompt': 'Responde en español.',
        })
        sandbox.write({'draft_message': 'Necesito una cotización en PDF y una actividad de seguimiento.'})
        with patch.object(
            type(self.env['ir.actions.report']), '_render_qweb_pdf',
            return_value=(b'%PDF-1.4 flujo completo', 'pdf'),
        ):
            sandbox.action_send_test_message()
        self.assertEqual(sandbox.state, 'done')
        self.assertEqual(sandbox.test_quote_id.state, 'draft')
        self.assertEqual(len(sandbox.test_attachment_ids), 1)
        self.assertEqual(len(sandbox.test_activity_ids), 1)
        assistant_line = sandbox.conversation_line_ids.filtered(
            lambda line: line.speaker == 'assistant')[-1]
        self.assertEqual(assistant_line.attachment_ids, sandbox.test_attachment_ids)
        self.assertIn('precio actual de Odoo', assistant_line.body)
        self.assertIn('20.00', assistant_line.body)
        self.assertEqual(assistant_line.body.count('precio actual de Odoo'), 1)
        self.assertEqual(sandbox.test_chat_message_id.channel_id, channel)
        self.assertEqual(sandbox.test_chat_message_id.attachment_ids, sandbox.test_attachment_ids)
        self.assertIn('precio actual de Odoo', sandbox.test_chat_message_id.body)
        self.assertEqual(sandbox.delivery_state, 'not_run')
        self.assertIn('PDF listo', sandbox.operational_result)
        self.assertIn('Actividad interna creada', sandbox.operational_result)

    def test_sandbox_analysis_uses_lab_transcript_and_published_knowledge(self):
        partner, channel = self._create_sandbox_channel('sandbox-brain-001')
        manual = self.env['ai.knowledge.base'].create({
            'name': 'Conocimiento QA implementacion',
            'source_type': 'text',
            'category': 'products',
            'source_text': (
                'Somos implementadores de Odoo. Ofrecemos implementación, '
                'desarrollo personalizado y acompañamiento comercial.'
            ),
            'publication_state': 'published',
        })
        manual.action_index()
        sandbox = self.env['chatroom.ai.sandbox'].create({
            'name': 'Prueba cerebro del laboratorio', 'channel_id': channel.id,
            'execution_mode': 'provider', 'prompt': 'Responde usando fuentes verificadas.',
        })
        self.env['chatroom.ai.sandbox.message'].create([
            {'sandbox_id': sandbox.id, 'sequence': 10, 'speaker': 'customer',
             'body': '¿Qué servicios de implementación ofrecen?'},
            {'sandbox_id': sandbox.id, 'sequence': 20, 'speaker': 'assistant',
             'body': 'Estoy revisando la información.'},
        ])
        with patch.object(
            type(channel), '_ai_chat_completion', return_value='Respuesta basada en conocimiento') as completion:
            sandbox.action_run()
        messages = completion.call_args.args[0]
        system = messages[0]['content']
        transcript = '\n'.join(message['content'] for message in messages[1:])
        self.assertIn('BASE DE CONOCIMIENTO AUTORIZADA', system)
        self.assertIn('implementadores de Odoo', system)
        self.assertIn('¿Qué servicios de implementación ofrecen?', transcript)
        self.assertIn('Conocimiento QA implementacion', sandbox.knowledge_sources)
        self.assertGreater(sandbox.knowledge_context_chars, 0)
        self.assertIn('publicada', sandbox.operational_result)
        self.assertEqual(sandbox.channel_id.partner_id, partner)

    def test_sandbox_meeting_request_creates_native_event_activity_and_visible_link(self):
        _partner, channel = self._create_sandbox_channel('sandbox-meeting-001')
        sandbox = self.env['chatroom.ai.sandbox'].create({
            'name': 'Prueba reunión nativa', 'channel_id': channel.id,
            'execution_mode': 'local', 'prompt': 'Responde en español.',
        })
        sandbox.write({'draft_message': 'Quiero agendar una reunión virtual y recibir el enlace.'})
        sandbox.action_send_test_message()
        self.assertTrue(sandbox.test_meeting_id)
        self.assertTrue(sandbox.test_meeting_link)
        self.assertTrue(self.env['calendar.event'].browse(sandbox.test_meeting_id).exists())
        self.assertTrue(sandbox.test_activity_ids)
        assistant = sandbox.conversation_line_ids.filtered(
            lambda line: line.speaker == 'assistant')[-1]
        self.assertIn(sandbox.test_meeting_link, assistant.body)
        self.assertIn('Reunión nativa creada', sandbox.operational_result)
        self.assertIn('Enlace:', sandbox.operational_result)

    def test_sandbox_analysis_materializes_native_actions_from_complete_transcript(self):
        _partner, channel = self._create_sandbox_channel('sandbox-analysis-actions-001')
        sandbox = self.env['chatroom.ai.sandbox'].create({
            'name': 'Analisis con acciones nativas', 'channel_id': channel.id,
            'execution_mode': 'local', 'prompt': 'Analiza y ejecuta las operaciones nativas seguras.',
        })
        self.env['chatroom.ai.sandbox.message'].create([
            {'sandbox_id': sandbox.id, 'sequence': 10, 'speaker': 'customer',
             'body': 'Necesito una reunion virtual y una actividad de seguimiento.'},
            {'sandbox_id': sandbox.id, 'sequence': 20, 'speaker': 'customer',
             'body': 'Por favor revisa todo y dejame el enlace aqui.'},
        ])
        with patch.object(type(channel), '_ai_chat_completion', return_value='Analisis completado'):
            sandbox.action_run()
        self.assertTrue(sandbox.test_meeting_id)
        self.assertTrue(sandbox.test_meeting_link)
        self.assertTrue(sandbox.test_activity_ids)
        self.assertIn('operaciones nativas sin enviar', sandbox.operational_result)
        self.assertIn(sandbox.test_meeting_link, sandbox.operational_result)

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

    def test_sandbox_provider_mode_uses_selected_model_without_delivery(self):
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('chatroom_whatsapp.ai_enabled', 'True')
        icp.set_param('chatroom_whatsapp.ai_provider_url', 'https://example.test/v1/chat/completions')
        icp.set_param('chatroom_whatsapp.ai_api_key', 'test-key')
        selected = self.env['chatroom.ai.provider.model'].create({
            'name': 'playground-provider-model', 'model_id': 'playground-provider-model',
            'provider': 'openai', 'supports_chat': True, 'active': True,
        })
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp', 'external_id': 'sandbox-playground-provider-001',
        })
        sandbox = self.env['chatroom.ai.sandbox'].create({
            'name': 'Laboratorio proveedor QA', 'channel_id': channel.id,
            'execution_mode': 'provider', 'provider_model_id': selected.id,
            'prompt': 'Responde en español y no inventes información.',
        })
        sandbox.write({'draft_message': 'Necesito una cotización de Odoo'})
        with patch.object(type(channel), '_ai_chat_completion', return_value='Respuesta IA de prueba') as completion:
            sandbox.action_send_test_message()
        self.assertEqual(completion.call_args.kwargs['model_id'], selected.id)
        self.assertEqual(sandbox.state, 'done')
        self.assertEqual(len(sandbox.conversation_line_ids), 2)
        self.assertEqual(sandbox.delivery_state, 'not_run')

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
        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(action['res_model'], 'chatroom.ai.usage.snapshot')

    def test_official_refresh_opens_populated_snapshot_with_cost_breakdown(self):
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('chatroom_whatsapp.ai_admin_api_key', 'admin-test-key')
        usage_model = self.env['chatroom.ai.usage.snapshot']
        usage_payload = {'data': [{'results': [{
            'num_model_requests': 3, 'input_tokens': 120,
            'output_tokens': 45, 'model': 'gpt-test',
        }]}]}
        cost_payload = {'data': [{'results': [{
            'line_item': 'Text generation',
            'amount': {'value': 0.12, 'currency': 'usd'},
        }]}]}
        with patch.object(type(usage_model), '_fetch', side_effect=[usage_payload, cost_payload]):
            action = usage_model.action_refresh()
        self.assertEqual(action['type'], 'ir.actions.act_window')
        snapshot = usage_model.browse(action['res_id'])
        self.assertEqual(snapshot.source, 'openai')
        self.assertEqual(snapshot.cost, 0.12)
        self.assertIn('Text generation', snapshot.cost_breakdown)

    def test_setup_wizard_persists_model_and_optional_funding(self):
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('chatroom_whatsapp.ai_api_key', 'test-key')
        model = self.env['chatroom.ai.provider.model'].create({
            'name': 'wizard-test-model', 'model_id': 'wizard-test-model',
            'provider': 'openai', 'supports_chat': True, 'active': True,
        })
        wizard = self.env['chatroom.ai.setup.wizard'].create({
            'provider_url': 'https://api.openai.com/v1',
            'selected_model_id': model.id,
            'create_company_knowledge': False,
            'initial_funding': 10.0,
        })
        action = wizard.action_finish()
        self.assertEqual(action['tag'], 'display_notification')
        self.assertEqual(icp.get_param('chatroom_whatsapp.ai_model_id'), str(model.id))
        self.assertEqual(self.env['chatroom.ai.funding'].search_count([
            ('reference', '=', 'Asistente inicial de IA'),
        ]), 1)

    def test_setup_wizard_rejects_negative_funding(self):
        with self.assertRaises(ValidationError):
            self.env['chatroom.ai.setup.wizard'].create({'initial_funding': -1.0})

    def test_setup_wizard_can_validate_official_costs_without_tokens(self):
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('chatroom_whatsapp.ai_api_key', 'test-key')
        icp.set_param('chatroom_whatsapp.ai_admin_api_key', 'admin-test-key')
        wizard = self.env['chatroom.ai.setup.wizard'].create({
            'provider_url': 'https://api.openai.com/v1',
            'create_company_knowledge': False,
        })
        usage_payload = {'data': [{'results': [{'num_model_requests': 4}]}]}
        cost_payload = {'data': [{'results': [{
            'amount': {'value': 0.08, 'currency': 'usd'},
        }]}]}
        with patch.object(
            type(self.env['chatroom.ai.usage.snapshot']), '_fetch',
            side_effect=[usage_payload, cost_payload],
        ):
            action = wizard.action_test_official_costs()
        self.assertEqual(action['params']['type'], 'success')
        self.assertIn('0.080000', action['params']['message'])

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
        self.assertEqual(snapshot.source, 'openai')
        self.assertTrue(snapshot.official_sync_at)

    def test_platform_connection_requires_admin_key(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'chatroom_whatsapp.ai_admin_api_key', False,
        )
        with self.assertRaises(UserError):
            self.env['chatroom.ai.usage.snapshot'].action_test_platform_connection()

    def test_billing_link_opens_official_platform(self):
        action = self.env['chatroom.ai.usage.snapshot'].action_open_platform_billing()
        self.assertEqual(action['type'], 'ir.actions.act_url')
        self.assertIn('platform.openai.com/settings/organization/billing', action['url'])

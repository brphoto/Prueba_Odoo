# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo.exceptions import UserError
from odoo.fields import Datetime
from odoo.tests import TransactionCase, tagged

from ..controllers.whatsapp_webhook import WhatsAppWebhookController


@tagged('post_install', '-at_install')
class TestChatroomWhatsapp(TransactionCase):

    def test_ai_boolean_parameters_and_approval_are_safe_by_default(self):
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp',
            'external_id': '573009991111',
        })
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('chatroom_whatsapp.ai_enabled', 'False')
        self.assertFalse(channel._ai_param_enabled('chatroom_whatsapp.ai_enabled'))
        icp.set_param('chatroom_whatsapp.ai_enabled', 'True')
        self.assertTrue(channel._ai_param_enabled('chatroom_whatsapp.ai_enabled'))
        icp.set_param('chatroom_whatsapp.ai_require_approval', False)
        self.assertTrue(channel._ai_requires_approval())
        channel._ai_stage_or_send_reply('Respuesta preparada')
        self.assertEqual(channel.ai_suggested_reply, 'Respuesta preparada')

    def test_ai_approval_can_be_disabled_explicitly(self):
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp',
            'external_id': '573009991112',
        })
        self.env['ir.config_parameter'].sudo().set_param(
            'chatroom_whatsapp.ai_require_approval', 'False')
        self.assertFalse(channel._ai_requires_approval())

    def test_find_or_create_dedupes_existing_partner_by_phone(self):
        """Un contacto ya existente con el mismo teléfono (importado de
        otra fuente, sin whatsapp_id todavía) no debe duplicarse."""
        partner = self.env['res.partner'].create({
            'name': "Cliente existente",
            'phone': "+57 300 123 4567",
        })
        channel = self.env['chatroom.channel']._find_or_create_from_webhook(
            'whatsapp', '573001234567', 'Nombre que manda WhatsApp')

        self.assertEqual(channel.partner_id, partner)
        self.assertEqual(partner.whatsapp_id, '573001234567')

    def test_find_or_create_creates_new_partner_when_no_match(self):
        channel = self.env['chatroom.channel']._find_or_create_from_webhook(
            'whatsapp', '573009998888', 'Contacto nuevo')

        self.assertEqual(channel.partner_id.whatsapp_id, '573009998888')
        self.assertEqual(channel.partner_id.name, 'Contacto nuevo')

    def test_find_or_create_is_idempotent_for_same_number(self):
        """Una segunda llamada con el mismo wa_id debe reusar el canal,
        no crear uno nuevo (evita duplicar conversaciones)."""
        channel1 = self.env['chatroom.channel']._find_or_create_from_webhook(
            'whatsapp', '573005554444', 'Ana')
        channel2 = self.env['chatroom.channel']._find_or_create_from_webhook(
            'whatsapp', '573005554444', 'Ana')

        self.assertEqual(channel1, channel2)

    def test_webhook_channel_gets_a_real_assignee(self):
        """Regresión: los canales creados desde el webhook (que corre con
        superusuario) deben asignarse a un agente real, no quedar en el
        usuario del sistema."""
        channel = self.env['chatroom.channel']._find_or_create_from_webhook(
            'whatsapp', '573001112222', 'Test asignación')

        self.assertTrue(channel.assigned_user_id)
        self.assertNotEqual(channel.assigned_user_id, self.env.ref('base.user_root'))

    def test_webhook_event_deduplication(self):
        """Meta reintenta la entrega de eventos; un mismo wa_message_id no
        debe procesarse dos veces."""
        partner = self.env['res.partner'].create({'name': "Cliente", 'phone': "+573001230000"})
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp',
            'external_id': '573001230000',
            'partner_id': partner.id,
        })
        self.env['chatroom.message'].create({
            'channel_id': channel.id,
            'direction': 'inbound',
            'message_type': 'text',
            'body': "Hola",
            'wa_message_id': 'wamid.YA_PROCESADO',
        })

        already = WhatsAppWebhookController._already_processed(self.env, 'wamid.YA_PROCESADO')
        self.assertTrue(already)

        not_yet = WhatsAppWebhookController._already_processed(self.env, 'wamid.NUEVO')
        self.assertFalse(not_yet)

    def test_opt_out_blocks_outbound_send(self):
        partner = self.env['res.partner'].create({
            'name': "Dado de baja",
            'phone': "+573007776666",
            'whatsapp_opt_out': True,
        })
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp',
            'external_id': '573007776666',
            'partner_id': partner.id,
        })

        with self.assertRaises(UserError):
            channel.action_send_text("Hola, ¿cómo estás?")

    def test_send_without_credentials_raises_user_error(self):
        """Sin token/Phone Number ID configurados, el envío debe fallar
        con un mensaje claro, no con un error técnico sin manejar."""
        self.env['ir.config_parameter'].sudo().set_param('chatroom_whatsapp.access_token', False)
        self.env['ir.config_parameter'].sudo().set_param('chatroom_whatsapp.phone_number_id', False)

        partner = self.env['res.partner'].create({'name': "Cliente", 'phone': "+573002221111"})
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp',
            'external_id': '573002221111',
            'partner_id': partner.id,
        })

        with self.assertRaises(UserError):
            channel.action_send_text("Hola")

    def test_mark_read_updates_message_state(self):
        """action_mark_read debe marcar los mensajes localmente incluso
        sin credenciales configuradas para el acuse remoto (no debe
        romper la UI)."""
        self.env['ir.config_parameter'].sudo().set_param('chatroom_whatsapp.access_token', False)

        partner = self.env['res.partner'].create({'name': "Cliente", 'phone': "+573004443333"})
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp',
            'external_id': '573004443333',
            'partner_id': partner.id,
        })
        message = self.env['chatroom.message'].create({
            'channel_id': channel.id,
            'direction': 'inbound',
            'message_type': 'text',
            'body': "Hola",
            'wa_message_id': 'wamid.SIN_LEER',
            'state': 'received',
        })

        channel.action_mark_read()

        self.assertEqual(message.state, 'read')

    def test_webhook_routes_to_matching_whatsapp_number(self):
        """Si hay una línea configurada con ese Phone Number ID, el canal
        nuevo debe quedar asociado a ella (multi-número)."""
        number = self.env['chatroom.whatsapp.number'].create({
            'name': "Soporte",
            'phone_number_id': '1112223330',
        })
        channel = self.env['chatroom.channel']._find_or_create_from_webhook(
            'whatsapp', '573008889999', 'Cliente de soporte',
            meta_phone_number_id='1112223330')

        self.assertEqual(channel.whatsapp_number_id, number)

    def test_webhook_without_matching_number_leaves_it_empty(self):
        """Sin líneas configuradas (o sin coincidencia), el canal se crea
        igual que antes, sin línea asociada (compatibilidad hacia atrás)."""
        channel = self.env['chatroom.channel']._find_or_create_from_webhook(
            'whatsapp', '573007778888', 'Cliente', meta_phone_number_id='no-existe')

        self.assertFalse(channel.whatsapp_number_id)

    def test_opt_keywords_flag_partner(self):
        partner = self.env['res.partner'].create({'name': "Cliente", 'phone': "+573006665555"})
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp',
            'external_id': '573006665555',
            'partner_id': partner.id,
        })
        message = self.env['chatroom.message'].create({
            'channel_id': channel.id,
            'direction': 'inbound',
            'message_type': 'text',
            'body': "STOP",
        })

        channel._handle_opt_keywords(message)

        self.assertTrue(partner.whatsapp_opt_out)

    def test_onboarding_wizard_saves_credentials_and_progresses(self):
        wizard = self.env['chatroom.whatsapp.onboarding.wizard'].create({
            'access_token': 'test-token-123',
            'phone_number_id': '999888777',
            'business_account_id': '111222333',
            'webhook_verify_token': 'my-verify-token',
        })
        self.assertEqual(wizard.state, 'intro')

        wizard.action_next()
        self.assertEqual(wizard.state, 'credentials')

        icp = self.env['ir.config_parameter'].sudo()
        wizard.action_next()
        self.assertEqual(wizard.state, 'webhook')
        self.assertEqual(icp.get_param('chatroom_whatsapp.access_token'), 'test-token-123')
        self.assertEqual(icp.get_param('chatroom_whatsapp.phone_number_id'), '999888777')

        wizard.action_next()
        self.assertEqual(wizard.state, 'test')
        self.assertEqual(icp.get_param('chatroom_whatsapp.webhook_verify_token'), 'my-verify-token')

        wizard.action_back()
        self.assertEqual(wizard.state, 'webhook')

    def test_onboarding_wizard_default_get_prefills_existing_config(self):
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('chatroom_whatsapp.phone_number_id', 'existing-phone-id')

        wizard = self.env['chatroom.whatsapp.onboarding.wizard'].create({})

        self.assertEqual(wizard.phone_number_id, 'existing-phone-id')

    def test_onboarding_wizard_test_connection_reports_failure_gracefully(self):
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('chatroom_whatsapp.access_token', False)
        icp.set_param('chatroom_whatsapp.phone_number_id', False)
        wizard = self.env['chatroom.whatsapp.onboarding.wizard'].create({'state': 'test'})

        wizard.action_test_connection()

        self.assertFalse(wizard.connection_ok)
        self.assertTrue(wizard.connection_result)

    def test_sla_state_none_without_inbound_messages(self):
        partner = self.env['res.partner'].create({'name': "Cliente SLA 1"})
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp', 'external_id': '573001110001', 'partner_id': partner.id,
        })
        self.assertEqual(channel.first_response_sla_state, 'none')

    def test_sla_turns_red_when_no_reply_past_threshold(self):
        partner = self.env['res.partner'].create({'name': "Cliente SLA 2"})
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp', 'external_id': '573001110002', 'partner_id': partner.id,
        })
        self.env['chatroom.message'].create({
            'channel_id': channel.id, 'direction': 'inbound', 'message_type': 'text',
            'body': "Hola, ¿tienen stock?", 'date': Datetime.now() - timedelta(minutes=90),
        })

        self.assertEqual(channel.first_response_sla_state, 'red')
        self.assertGreaterEqual(channel.pending_response_minutes, 60)

    def test_sla_turns_green_once_agent_replies(self):
        partner = self.env['res.partner'].create({'name': "Cliente SLA 3"})
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp', 'external_id': '573001110003', 'partner_id': partner.id,
        })
        inbound_date = Datetime.now() - timedelta(minutes=90)
        self.env['chatroom.message'].create({
            'channel_id': channel.id, 'direction': 'inbound', 'message_type': 'text',
            'body': "Hola", 'date': inbound_date,
        })
        self.env['chatroom.message'].create({
            'channel_id': channel.id, 'direction': 'outbound', 'message_type': 'text',
            'body': "¡Hola! Sí, tenemos stock.", 'date': inbound_date + timedelta(minutes=5),
        })

        self.assertEqual(channel.first_response_sla_state, 'green')
        self.assertEqual(channel.pending_response_minutes, 0)
        self.assertEqual(channel.first_response_minutes, 5.0)

    def test_sla_breach_cron_notifies_once_and_resets_on_reply(self):
        agent = self.env['res.users'].create({
            'name': "Agente SLA", 'login': 'agente_sla_test', 'email': 'agente_sla_test@example.com',
        })
        partner = self.env['res.partner'].create({'name': "Cliente SLA 4"})
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp', 'external_id': '573001110004', 'partner_id': partner.id,
            'assigned_user_id': agent.id, 'state': 'open',
        })
        self.env['chatroom.message'].create({
            'channel_id': channel.id, 'direction': 'inbound', 'message_type': 'text',
            'body': "Hola", 'date': Datetime.now() - timedelta(minutes=90),
        })

        def chatter_count():
            # 'message_ids' en chatroom.channel está tapado por el
            # One2many propio a chatroom.message (las burbujas del chat);
            # el aviso del cron se manda por el chatter de mail.thread,
            # que solo se puede contar buscando mail.message por afuera.
            return self.env['mail.message'].search_count(
                [('model', '=', 'chatroom.channel'), ('res_id', '=', channel.id)])

        chatter_before = chatter_count()

        self.env['chatroom.channel']._cron_notify_sla_breach()
        self.assertTrue(channel.sla_breach_notified)
        self.assertGreater(chatter_count(), chatter_before)

        chatter_after_first_run = chatter_count()
        self.env['chatroom.channel']._cron_notify_sla_breach()
        self.assertEqual(chatter_count(), chatter_after_first_run,
                          "no debe mandar un segundo aviso mientras siga en rojo")

        self.env['chatroom.message'].create({
            'channel_id': channel.id, 'direction': 'outbound', 'message_type': 'text', 'body': "Ya te respondo",
        })
        self.env['chatroom.channel']._cron_notify_sla_breach()
        self.assertFalse(channel.sla_breach_notified)

    def test_close_without_credentials_does_not_raise(self):
        """Cerrar la conversación dispara la encuesta de satisfacción,
        pero si falla el envío (sin credenciales configuradas) el cierre
        en sí no debe romperse."""
        self.env['ir.config_parameter'].sudo().set_param('chatroom_whatsapp.access_token', False)
        self.env['ir.config_parameter'].sudo().set_param('chatroom_whatsapp.phone_number_id', False)
        partner = self.env['res.partner'].create({'name': "Cliente CSAT 1"})
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp', 'external_id': '573001120001', 'partner_id': partner.id,
        })
        self.env['chatroom.message'].create({
            'channel_id': channel.id, 'direction': 'inbound', 'message_type': 'text', 'body': "Hola",
        })

        channel.action_close()

        self.assertEqual(channel.state, 'closed')
        self.assertFalse(channel.csat_requested)

    def test_csat_reply_records_score(self):
        partner = self.env['res.partner'].create({'name': "Cliente CSAT 2"})
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp', 'external_id': '573001120002', 'partner_id': partner.id,
            'csat_requested': True,
        })

        channel._handle_interactive_reply('interactive', {
            'interactive': {'list_reply': {'id': 'csat_4', 'title': '⭐⭐⭐⭐'}},
        })

        self.assertEqual(channel.csat_score, 4)
        self.assertFalse(channel.csat_requested)
        self.assertTrue(channel.csat_answered_at)

    def test_csat_reply_ignored_when_no_survey_pending(self):
        """Sin una encuesta pendiente (csat_requested=False), un mensaje
        interactivo cualquiera no debe poder 'inventar' una calificación."""
        partner = self.env['res.partner'].create({'name': "Cliente CSAT 3"})
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp', 'external_id': '573001120003', 'partner_id': partner.id,
        })

        channel._handle_interactive_reply('interactive', {
            'interactive': {'list_reply': {'id': 'csat_5', 'title': '⭐⭐⭐⭐⭐'}},
        })

        self.assertFalse(channel.csat_score)

    def test_catalog_reply_adds_product_to_cart(self):
        if 'product.product' not in self.env:
            self.skipTest("Módulo de productos no instalado")
        product = self.env['product.product'].create({
            'name': "Producto de catálogo test", 'list_price': 10.0})
        partner = self.env['res.partner'].create({'name': "Cliente Catálogo"})
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp', 'external_id': '573001120004', 'partner_id': partner.id,
        })

        channel._handle_interactive_reply('interactive', {
            'interactive': {'list_reply': {'id': f'prod_{product.id}', 'title': product.name}},
        })

        self.assertEqual(len(channel.cart_line_ids), 1)
        self.assertEqual(channel.cart_line_ids.product_id, product.id)

    def test_send_product_catalog_creates_list_message(self):
        if 'product.product' not in self.env:
            self.skipTest("Módulo de productos no instalado")
        self.env['ir.config_parameter'].sudo().set_param('chatroom_whatsapp.access_token', False)
        self.env['ir.config_parameter'].sudo().set_param('chatroom_whatsapp.phone_number_id', False)
        product = self.env['product.product'].create({'name': "Producto catálogo", 'list_price': 5.0})
        partner = self.env['res.partner'].create({'name': "Cliente Catálogo 2"})
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp', 'external_id': '573001120005', 'partner_id': partner.id,
        })

        with self.assertRaises(UserError):
            channel.action_send_product_catalog(product.ids)

    def test_dashboard_data_includes_sla_and_csat_aggregates(self):
        partner = self.env['res.partner'].create({'name': "Cliente Dashboard"})
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp', 'external_id': '573001130001', 'partner_id': partner.id,
        })
        inbound_date = Datetime.now() - timedelta(days=1)
        self.env['chatroom.message'].create({
            'channel_id': channel.id, 'direction': 'inbound', 'message_type': 'text',
            'body': "Hola", 'date': inbound_date,
        })
        self.env['chatroom.message'].create({
            'channel_id': channel.id, 'direction': 'outbound', 'message_type': 'text',
            'body': "Hola, ¿en qué te ayudo?", 'date': inbound_date + timedelta(minutes=10),
        })
        channel.write({'csat_score': 4, 'csat_answered_at': Datetime.now()})

        data = self.env['chatroom.channel'].get_dashboard_data()

        self.assertIsNotNone(data['sla_compliance_rate'])
        self.assertGreaterEqual(data['sla_answered_count'], 1)
        self.assertGreaterEqual(data['csat_answered_count'], 1)
        self.assertGreater(data['avg_csat_score'], 0)

    def test_transcript_pdf_data_is_bounded_and_ordered(self):
        """El PDF no debe materializar todo el historial de una conversación."""
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp', 'external_id': '573001130002',
        })
        for index in range(8):
            self.env['chatroom.message'].create({
                'channel_id': channel.id,
                'direction': 'inbound' if index % 2 == 0 else 'outbound',
                'message_type': 'text',
                'body': f'Mensaje {index}',
                'date': Datetime.now() - timedelta(minutes=8 - index),
            })
        self.env['ir.config_parameter'].sudo().set_param(
            'chatroom_whatsapp.transcript_pdf_max_messages', '50')

        data = channel.get_transcript_report_data(limit=5)

        self.assertEqual(data['total'], 8)
        self.assertEqual(data['shown'], 5)
        self.assertTrue(data['truncated'])
        self.assertEqual(data['lines'][0]['body'], 'Mensaje 3')
        self.assertEqual(data['lines'][-1]['body'], 'Mensaje 7')

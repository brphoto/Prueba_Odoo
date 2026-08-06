# -*- coding: utf-8 -*-
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from ..controllers.whatsapp_webhook import WhatsAppWebhookController


@tagged('post_install', '-at_install')
class TestChatroomWhatsapp(TransactionCase):

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

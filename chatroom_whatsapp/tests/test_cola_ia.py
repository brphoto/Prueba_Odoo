# -*- coding: utf-8 -*-
"""Cola de respuestas de IA: agrupa mensajes seguidos, sobrevive a un
reinicio (vive en la base) y reintenta si algo falla."""
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import TransactionCase, tagged

from ..controllers.whatsapp_webhook import WhatsAppWebhookController


@tagged('post_install', '-at_install')
class TestColaIA(TransactionCase):

    def setUp(self):
        super().setUp()
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('chatroom_whatsapp.ai_queue', 'True')
        icp.set_param('chatroom_whatsapp.ai_debounce_seconds', '6')
        icp.set_param('chatroom_whatsapp.ai_max_wait_seconds', '20')
        self.Channel = type(self.env['chatroom.channel'])
        self.processed = []
        patcher = patch.object(self.Channel, '_ai_process_inbound_message', autospec=True,
                               side_effect=lambda channel, message: self.processed.append(
                                   (channel.id, message.body)) or {'status': 'sent'})
        patcher.start()
        self.addCleanup(patcher.stop)
        typing = patch.object(self.Channel, '_ai_send_typing_indicator', autospec=True, return_value=True)
        self.typing = typing.start()
        self.addCleanup(typing.stop)
        away = patch.object(self.Channel, '_maybe_send_away_message', autospec=True, return_value=False)
        away.start()
        self.addCleanup(away.stop)

    def _webhook(self, *texts, wa_id='593990001111'):
        messages = [{'from': wa_id, 'id': 'wamid.COLA%s%s' % (wa_id, index), 'type': 'text',
                     'text': {'body': text}} for index, text in enumerate(texts, start=len(self.processed) * 10)]
        payload = {'object': 'whatsapp_business_account', 'entry': [{'changes': [{'value': {
            'contacts': [{'wa_id': wa_id, 'profile': {'name': 'Cliente Cola'}}], 'messages': messages}}]}]}
        WhatsAppWebhookController().process_payload(self.env, payload, ai_message_queue=[])
        return self.env['chatroom.channel'].search([('external_id', '=', wa_id)], limit=1)

    def _expire(self, channel):
        channel.ai_reply_due_at = fields.Datetime.now() - timedelta(seconds=1)

    def test_webhook_enqueues_instead_of_answering_at_once(self):
        channel = self._webhook('hola')
        self.assertFalse(self.processed, 'No responde dentro del webhook.')
        self.assertTrue(channel.ai_reply_due_at)
        wait = (channel.ai_reply_due_at - fields.Datetime.now()).total_seconds()
        self.assertTrue(3 <= wait <= 7, wait)
        cron = self.env.ref('chatroom_whatsapp.ir_cron_ai_reply_queue')
        self.assertTrue(self.env['ir.cron.trigger'].search([('cron_id', '=', cron.id)]))

    def test_burst_is_answered_once_with_the_last_message(self):
        channel = self._webhook('hola', 'quería saber', '¿cuánto cuesta la silla?')
        self._expire(channel)
        self.env['chatroom.channel']._cron_process_ai_queue()
        self.assertEqual(self.processed, [(channel.id, '¿cuánto cuesta la silla?')])
        self.assertFalse(channel.ai_reply_due_at)
        self.typing.assert_called_once()
        self.assertEqual([message.body for message in channel._ai_pending_inbound()],
                         ['hola', 'quería saber', '¿cuánto cuesta la silla?'])
        # Nada vencido: no vuelve a responder.
        self.env['chatroom.channel']._cron_process_ai_queue()
        self.assertEqual(len(self.processed), 1)

    def test_new_message_extends_wait_up_to_a_limit(self):
        channel = self._webhook('hola')
        started = fields.Datetime.now() - timedelta(seconds=18)
        channel.write({'ai_burst_started_at': started})
        channel._ai_enqueue_inbound(channel.message_ids[-1:])
        # Tope: 20 s desde el primer mensaje, aunque siga escribiendo.
        self.assertLessEqual(channel.ai_reply_due_at, started + timedelta(seconds=20))
        self.assertEqual(channel.ai_burst_started_at, started)

    def test_pending_only_counts_messages_after_last_reply(self):
        channel = self._webhook('primera consulta')
        self.env['chatroom.message'].create({'channel_id': channel.id, 'direction': 'outbound',
                                             'body': 'Respuesta', 'state': 'sent'})
        self.env['chatroom.message'].create({'channel_id': channel.id, 'direction': 'inbound',
                                             'body': 'otra cosa', 'state': 'received'})
        self.assertEqual(channel._ai_pending_inbound().mapped('body'), ['otra cosa'])

    def test_failure_is_retried_then_dropped(self):
        channel = self._webhook('hola')
        with patch.object(self.Channel, '_ai_process_queued', autospec=True, side_effect=RuntimeError('caída')):
            for attempt in range(1, 4):
                self._expire(channel)
                self.env['chatroom.channel']._cron_process_ai_queue()
                self.assertEqual(channel.ai_queue_attempts, attempt)
        self.assertFalse(channel.ai_reply_due_at, 'Tras 3 intentos se deja de reintentar.')

    def test_queue_can_be_disabled(self):
        self.env['ir.config_parameter'].sudo().set_param('chatroom_whatsapp.ai_queue', 'False')
        queue = []
        payload = {'object': 'whatsapp_business_account', 'entry': [{'changes': [{'value': {
            'contacts': [{'wa_id': '593990002222', 'profile': {'name': 'Sin cola'}}],
            'messages': [{'from': '593990002222', 'id': 'wamid.SINCOLA1', 'type': 'text', 'text': {'body': 'hola'}}],
        }}]}]}
        WhatsAppWebhookController().process_payload(self.env, payload, ai_message_queue=queue)
        channel = self.env['chatroom.channel'].search([('external_id', '=', '593990002222')])
        self.assertEqual(len(queue), 1, 'Sin cola vuelve al procesamiento anterior.')
        self.assertFalse(channel.ai_reply_due_at)

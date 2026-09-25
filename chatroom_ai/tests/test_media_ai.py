# -*- coding: utf-8 -*-
"""Audios e imágenes: la IA los lee antes de responder."""
import base64
from unittest.mock import MagicMock, patch

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestMediaAi(TransactionCase):

    def setUp(self):
        super().setUp()
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('chatroom_whatsapp.ai_enabled', 'True')
        icp.set_param('chatroom_whatsapp.ai_provider_url', 'https://ia.invalid/v1')
        icp.set_param('chatroom_whatsapp.ai_api_key', 'clave-de-prueba')
        self.channel = self.env['chatroom.channel'].create({'channel_type': 'whatsapp', 'external_id': '593990003333'})

    def _message(self, message_type, mimetype, body=''):
        attachment = self.env['ir.attachment'].create({
            'name': 'adjunto', 'raw': b'datos-de-prueba', 'mimetype': mimetype})
        return self.env['chatroom.message'].create({
            'channel_id': self.channel.id, 'direction': 'inbound', 'message_type': message_type,
            'body': body, 'state': 'received', 'attachment_ids': [(6, 0, attachment.ids)]})

    def test_audio_is_transcribed_and_read_by_the_ai(self):
        message = self._message('audio', 'audio/ogg; codecs=opus')
        response = MagicMock(status_code=200)
        response.json.return_value = {'text': 'Hola, quiero saber el precio de la silla'}
        with patch('odoo.addons.chatroom_ai.models.chatroom_media.requests.post', return_value=response) as post:
            self.channel._ai_prepare_pending_media(message)
        self.assertTrue(post.call_args.args[0].endswith('/v1/audio/transcriptions'))
        filename = post.call_args.kwargs['files']['file'][0]
        self.assertEqual(filename, 'audio.ogg')
        self.assertEqual(message.ai_transcript, 'Hola, quiero saber el precio de la silla')
        self.assertEqual(message._ai_text(), '[Audio] Hola, quiero saber el precio de la silla')
        conversation = self.channel._ai_build_conversation()
        self.assertIn('[Audio] Hola, quiero saber el precio', conversation[-1]['content'])
        # Ya transcrito: no se vuelve a pagar.
        with patch('odoo.addons.chatroom_ai.models.chatroom_media.requests.post') as post:
            self.channel._ai_prepare_pending_media(message)
        post.assert_not_called()

    def test_image_is_described_with_its_caption(self):
        message = self._message('image', 'image/jpeg', body='¿tienen este modelo?')
        with patch.object(type(self.channel), '_ai_chat_completion', autospec=True,
                          return_value='Silla de oficina negra con apoyabrazos.') as completion:
            self.channel._ai_prepare_pending_media(message)
        content = completion.call_args.args[1][1]['content']
        self.assertEqual(content[0]['text'], '¿tienen este modelo?')
        self.assertTrue(content[1]['image_url']['url'].startswith(
            'data:image/jpeg;base64,%s' % base64.b64encode(b'datos-de-prueba').decode()))
        self.assertEqual(message._ai_text(), '¿tienen este modelo?\n[Imagen] Silla de oficina negra con apoyabrazos.')

    def test_failures_and_switches_never_block_the_reply(self):
        message = self._message('audio', 'audio/ogg')
        with patch('odoo.addons.chatroom_ai.models.chatroom_media.requests.post', side_effect=RuntimeError('caída')):
            self.channel._ai_prepare_pending_media(message)
        self.assertFalse(message.ai_transcript)
        self.env['ir.config_parameter'].sudo().set_param('chatroom_ai.transcribe_audio', 'False')
        with patch('odoo.addons.chatroom_ai.models.chatroom_media.requests.post') as post:
            self.channel._ai_prepare_pending_media(message)
        post.assert_not_called()

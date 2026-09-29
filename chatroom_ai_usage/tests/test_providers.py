# -*- coding: utf-8 -*-
"""Proveedores de IA: OpenAI y Meta Model API (Muse), con proveedor aparte
para audio y búsqueda. Todo simulado: no hace falta una clave real."""
import json
from unittest.mock import Mock, patch

from odoo.tests import TransactionCase, tagged

MEDIA = 'odoo.addons.chatroom_ai.models.chatroom_media'
CATALOG = 'odoo.addons.chatroom_ai_usage.models.chatroom_ai_provider_model.requests.get'


def chat_response(content='Hola', usage=None):
    response = Mock(status_code=200)
    response.json.return_value = {'choices': [{'message': {'content': content}}], 'usage': usage or {}}
    return response


@tagged('post_install', '-at_install')
class TestAiProviders(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.icp = cls.env['ir.config_parameter'].sudo()
        cls.channel = cls.env['chatroom.channel'].create({
            'channel_type': 'whatsapp', 'external_id': 'provider-tests-001'})

    def _use(self, url, model, key='clave-prueba'):
        for param, value in {
            'chatroom_whatsapp.ai_enabled': 'True', 'chatroom_whatsapp.ai_provider_url': url,
            'chatroom_whatsapp.ai_api_key': key, 'chatroom_whatsapp.ai_model': model,
            'chatroom_whatsapp.ai_model_id': '', 'chatroom_whatsapp.ai_reasoning_effort': '',
            'chatroom_ai.media_provider_url': '', 'chatroom_ai.media_api_key': '',
        }.items():
            self.icp.set_param(param, value)

    def _chat(self, usage=None):
        with patch.object(type(self.channel), '_meta_request', return_value=chat_response(usage=usage)) as request:
            self.channel._ai_chat_completion([{'role': 'user', 'content': 'Hola'}])
        return request.call_args

    # ------------------------------------------------------------------
    # Chat
    # ------------------------------------------------------------------
    def test_meta_chat_uses_same_format_and_low_reasoning(self):
        self._use('https://api.meta.ai/v1', 'muse-spark-1.3')
        call = self._chat()
        self.assertEqual(call.args[1], 'https://api.meta.ai/v1/chat/completions')
        self.assertEqual(call.kwargs['json']['model'], 'muse-spark-1.3')
        self.assertEqual(call.kwargs['json']['reasoning_effort'], 'low',
                         'Muse Spark siempre razona: por defecto, lo mínimo útil.')

    def test_reasoning_effort_setting(self):
        self._use('https://api.openai.com/v1', 'gpt-4o-mini')
        self.assertNotIn('reasoning_effort', self._chat().kwargs['json'], 'gpt-4o-mini no razona.')
        self.icp.set_param('chatroom_whatsapp.ai_reasoning_effort', 'medium')
        self.assertEqual(self._chat().kwargs['json']['reasoning_effort'], 'medium')
        self._use('https://api.meta.ai/v1', 'muse-spark-1.3')
        self.icp.set_param('chatroom_whatsapp.ai_reasoning_effort', 'off')
        self.assertNotIn('reasoning_effort', self._chat().kwargs['json'])

    def test_meta_cost_uses_cached_input_price(self):
        self._use('https://api.meta.ai/v1', 'muse-spark-1.3')
        Model = self.env['chatroom.ai.provider.model']
        Model.search([('model_id', '=', 'muse-spark-1.3')]).unlink()
        prices = Model._published_pricing('muse-spark-1.3')
        Model.create({'name': 'muse-spark-1.3', 'model_id': 'muse-spark-1.3', 'provider': 'meta',
                      'supports_chat': True, 'input_price_per_million': prices[0],
                      'output_price_per_million': prices[1], 'cached_input_price_per_million': prices[2]})
        self._chat(usage={'prompt_tokens': 1000000, 'completion_tokens': 100000, 'total_tokens': 1100000,
                          'prompt_tokens_details': {'cached_tokens': 800000}})
        event = self.env['chatroom.ai.usage.event'].search([('model', '=', 'muse-spark-1.3')], limit=1,
                                                          order='id desc')
        # 200k a 1.25 + 800k a 0.15 + 100k a 4.25 = 0.25 + 0.12 + 0.425
        self.assertAlmostEqual(event.estimated_cost, 0.795, places=6)
        self.assertEqual(event.cached_tokens, 800000)

    def test_openai_cost_without_cached_price_keeps_general_discount(self):
        self._use('https://api.openai.com/v1', 'modelo-sin-cache')
        self.env['chatroom.ai.provider.model'].create({
            'name': 'modelo-sin-cache', 'model_id': 'modelo-sin-cache', 'supports_chat': True,
            'input_price_per_million': 1.0, 'output_price_per_million': 0.0})
        self.icp.set_param('chatroom_ai_usage.cached_input_discount', '0.5')
        self._chat(usage={'prompt_tokens': 1000000, 'completion_tokens': 0,
                          'prompt_tokens_details': {'cached_tokens': 1000000}})
        event = self.env['chatroom.ai.usage.event'].search([('model', '=', 'modelo-sin-cache')], limit=1)
        self.assertAlmostEqual(event.estimated_cost, 0.5, places=6)

    # ------------------------------------------------------------------
    # Catálogo
    # ------------------------------------------------------------------
    def test_sync_meta_catalog_prefills_prices_and_hides_contributor(self):
        self._use('https://api.meta.ai/v1', 'muse-spark-1.3')
        response = Mock(status_code=200)
        response.json.return_value = {'data': [
            {'id': 'muse-spark-1.3', 'owned_by': 'meta'}, {'id': 'muse-spark-1.3-contributor', 'owned_by': 'meta'},
            {'id': 'muse-voice-transcribe-1.0', 'owned_by': 'meta'}]}
        Model = self.env['chatroom.ai.provider.model']
        with patch(CATALOG, return_value=response) as get:
            Model.action_sync_from_provider()
        self.assertEqual(get.call_args.args[0], 'https://api.meta.ai/v1/models')
        spark = Model.search([('model_id', '=', 'muse-spark-1.3')])
        self.assertEqual((spark.provider, spark.supports_chat, spark.recommended), ('meta', True, True))
        self.assertEqual((spark.input_price_per_million, spark.output_price_per_million,
                          spark.cached_input_price_per_million), (1.25, 4.25, 0.15))
        contributor = Model.search([('model_id', '=', 'muse-spark-1.3-contributor')])
        self.assertFalse(contributor.supports_chat, 'Meta entrena con esas conversaciones.')
        self.assertFalse(Model.search([('model_id', '=', 'muse-voice-transcribe-1.0')]).supports_chat)
        spark.input_price_per_million = 2.0  # lo que el administrador configure se respeta
        with patch(CATALOG, return_value=response):
            Model.action_sync_from_provider()
        self.assertEqual(spark.input_price_per_million, 2.0)

    # ------------------------------------------------------------------
    # Audio, voz y búsqueda
    # ------------------------------------------------------------------
    def test_meta_has_no_voice_nor_embeddings_unless_media_provider(self):
        self._use('https://api.meta.ai/v1', 'muse-spark-1.3')
        channel = self.channel
        self.assertEqual(channel._ai_provider_base('chat'), ('https://api.meta.ai/v1', 'clave-prueba'))
        self.assertEqual(channel._ai_provider_base('audio'), ('https://api.meta.ai/v1', 'clave-prueba'))
        self.assertIsNone(channel._ai_provider_base('speech'))
        self.assertIsNone(channel._ai_provider_base('embeddings'))
        self.icp.set_param('chatroom_ai.media_provider_url', 'https://api.openai.com/v1')
        self.icp.set_param('chatroom_ai.media_api_key', 'clave-openai')
        for purpose in ('audio', 'speech', 'embeddings'):
            self.assertEqual(channel._ai_provider_base(purpose), ('https://api.openai.com/v1', 'clave-openai'))
        self.assertEqual(channel._ai_provider_base('chat')[0], 'https://api.meta.ai/v1')

    def test_openai_keeps_everything_in_one_provider(self):
        self._use('https://api.openai.com/v1', 'gpt-4o-mini')
        for purpose in ('audio', 'speech', 'embeddings'):
            self.assertEqual(self.channel._ai_provider_base(purpose)[0], 'https://api.openai.com/v1')

    def _audio(self, raw=b'OggS-audio', mimetype='audio/ogg'):
        return self.env['ir.attachment'].create({'name': 'nota', 'raw': raw, 'mimetype': mimetype})

    def test_meta_transcription_sends_wav_with_request_json(self):
        self._use('https://api.meta.ai/v1', 'muse-spark-1.3')
        response = Mock(status_code=200)
        response.json.return_value = {'sessionId': 's1', 'transcript': 'Quiero cotizar un seguro',
                                      'audioDurationMs': 1800, 'turns': []}
        Channel = type(self.channel)
        with patch.object(Channel, '_ai_ffmpeg', return_value='ffmpeg'), \
                patch('%s.to_wav' % MEDIA, return_value=b'RIFF-wav') as convert, \
                patch('%s.requests.post' % MEDIA, return_value=response) as post:
            text = self.channel._ai_transcribe_audio(self._audio())
        self.assertEqual(text, 'Quiero cotizar un seguro')
        convert.assert_called_once()
        self.assertEqual(post.call_args.args[0], 'https://api.meta.ai/v1/asr/transcribe')
        files = post.call_args.kwargs['files']
        settings = json.loads(files['request'][1])
        self.assertEqual((settings['model'], settings['audioEncoding']), ('muse-voice-transcribe-1.0', 'WAV'))
        self.assertEqual(files['audio'], ('audio.wav', b'RIFF-wav', 'audio/wav'))

    def test_meta_transcription_without_ffmpeg_does_not_break(self):
        self._use('https://api.meta.ai/v1', 'muse-spark-1.3')
        with patch.object(type(self.channel), '_ai_ffmpeg', return_value=None), \
                patch('%s.requests.post' % MEDIA) as post:
            self.assertEqual(self.channel._ai_transcribe_audio(self._audio()), '')
        post.assert_not_called()
        # Un WAV no necesita conversión.
        response = Mock(status_code=200)
        response.json.return_value = {'transcript': 'hola', 'sessionId': 's', 'audioDurationMs': 1, 'turns': []}
        with patch.object(type(self.channel), '_ai_ffmpeg', return_value=None), \
                patch('%s.requests.post' % MEDIA, return_value=response):
            self.assertEqual(self.channel._ai_transcribe_audio(self._audio(b'RIFF', 'audio/wav')), 'hola')

    def test_media_provider_transcribes_with_whisper_while_chat_is_meta(self):
        self._use('https://api.meta.ai/v1', 'muse-spark-1.3')
        self.icp.set_param('chatroom_ai.media_provider_url', 'https://api.openai.com/v1')
        self.icp.set_param('chatroom_ai.media_api_key', 'clave-openai')
        response = Mock(status_code=200)
        response.json.return_value = {'text': 'audio con whisper'}
        with patch('%s.requests.post' % MEDIA, return_value=response) as post:
            self.assertEqual(self.channel._ai_transcribe_audio(self._audio()), 'audio con whisper')
        self.assertEqual(post.call_args.args[0], 'https://api.openai.com/v1/audio/transcriptions')
        self.assertEqual(post.call_args.kwargs['headers']['Authorization'], 'Bearer clave-openai')

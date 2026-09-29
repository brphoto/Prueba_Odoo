# -*- coding: utf-8 -*-
import base64
import json
import logging
import shutil
import subprocess

import requests

from odoo import _, models

_logger = logging.getLogger(__name__)

AUDIO_LIMIT = 24 * 1024 * 1024   # tope del endpoint de transcripción
IMAGE_LIMIT = 8 * 1024 * 1024
# El endpoint deduce el formato por la extensión del archivo.
AUDIO_EXTENSIONS = {
    'audio/ogg': 'ogg', 'audio/opus': 'ogg', 'audio/mpeg': 'mp3', 'audio/mp3': 'mp3', 'audio/mp4': 'm4a',
    'audio/x-m4a': 'm4a', 'audio/aac': 'm4a', 'audio/wav': 'wav', 'audio/x-wav': 'wav', 'audio/webm': 'webm',
    'audio/amr': 'ogg',
}
# Lo que cada proveedor ofrece además del chat. Meta (Muse) transcribe con su
# propio endpoint (solo WAV) y no tiene voz ni embeddings.
PROVIDER_MEDIA = {
    'openai': {'audio', 'speech', 'embeddings'},
    'compatible': {'audio', 'speech', 'embeddings'},
    'meta': {'audio'},
}
META_ASR_MODEL = 'muse-voice-transcribe-1.0'


def to_wav(raw, ffmpeg):
    """Audio de WhatsApp (ogg/opus) a WAV mono 16 kHz, lo único que acepta Meta."""
    process = subprocess.run(
        [ffmpeg, '-hide_banner', '-loglevel', 'error', '-i', 'pipe:0', '-ac', '1', '-ar', '16000',
         '-f', 'wav', 'pipe:1'], input=raw, capture_output=True, timeout=60, check=False)
    if process.returncode or not process.stdout:
        raise ValueError((process.stderr or b'ffmpeg sin salida').decode('utf-8', 'replace')[:200])
    return process.stdout


class ChatroomChannel(models.Model):
    _inherit = 'chatroom.channel'

    def _ai_prepare_pending_media(self, messages):
        """Transcribe audios y describe imágenes para que la IA los entienda.

        Un fallo nunca frena la respuesta: el mensaje queda sin transcripción
        y la IA responde con lo que tenga.
        """
        result = super()._ai_prepare_pending_media(messages)
        for message in messages:
            if message.direction != 'inbound' or message.ai_transcript or not message.attachment_ids:
                continue
            attachment = message.attachment_ids[:1]
            try:
                if message.message_type == 'audio' and self._ai_param_enabled(
                        'chatroom_ai.transcribe_audio', default=True):
                    text = self._ai_transcribe_audio(attachment)
                elif message.message_type == 'image' and self._ai_param_enabled(
                        'chatroom_ai.describe_images', default=True):
                    text = self._ai_describe_image(attachment, message.body)
                else:
                    continue
            except Exception as exc:  # noqa: BLE001 - la respuesta sigue sin el adjunto
                _logger.info('No se pudo leer el adjunto del mensaje %s: %s', message.id, exc)
                continue
            if text and text.strip():
                message.sudo().ai_transcript = text.strip()[:4000]
        return result

    def _ai_provider_base(self, purpose='chat'):
        """(url base, clave) del proveedor para ``purpose``, sin /chat/completions.

        ``purpose``: chat, audio (transcribir), speech (voz) o embeddings. Para
        los tres últimos se usa el proveedor de audio de Ajustes si existe; si
        no, el principal, siempre que lo ofrezca. None: no disponible.
        """
        if purpose != 'chat':
            icp = self.env['ir.config_parameter'].sudo()
            media_url = (icp.get_param('chatroom_ai.media_provider_url') or '').strip().rstrip('/')
            media_key = icp.get_param('chatroom_ai.media_api_key')
            if media_url and media_key and self._ai_param_enabled('chatroom_whatsapp.ai_enabled'):
                base = media_url.removesuffix('/chat/completions')
                return (base, media_key) if purpose in PROVIDER_MEDIA[self._ai_provider_kind(base)] else None
        credentials = self._ai_get_credentials()
        if not credentials or not credentials[0] or not credentials[1]:
            return None
        base = credentials[0].rstrip('/')
        if base.endswith('/chat/completions'):
            base = base[:-len('/chat/completions')]
        if purpose != 'chat' and purpose not in PROVIDER_MEDIA[self._ai_provider_kind(base)]:
            return None
        return base, credentials[1]

    def _ai_transcribe_audio(self, attachment):
        raw = attachment.raw
        provider = self._ai_provider_base('audio')
        if not raw or len(raw) > AUDIO_LIMIT or not provider:
            return ''
        base, key = provider
        mimetype = (attachment.mimetype or 'audio/ogg').split(';')[0].strip()
        if self._ai_provider_kind(base) == 'meta':
            return self._ai_transcribe_meta(raw, mimetype, base, key)
        filename = 'audio.%s' % AUDIO_EXTENSIONS.get(mimetype, 'ogg')
        model = self.env['ir.config_parameter'].sudo().get_param('chatroom_ai.transcription_model', 'whisper-1')
        response = requests.post(
            '%s/audio/transcriptions' % base, headers={'Authorization': 'Bearer %s' % key},
            files={'file': (filename, raw, mimetype)}, data={'model': model}, timeout=90)
        response.raise_for_status()
        return (response.json() or {}).get('text') or ''

    def _ai_ffmpeg(self):
        path = self.env['ir.config_parameter'].sudo().get_param('chatroom_ai.ffmpeg_path')
        return path or shutil.which('ffmpeg')

    def _ai_transcribe_meta(self, raw, mimetype, base, key):
        """Muse Voice Transcribe: multipart con «request» (JSON) y «audio» (WAV)."""
        if mimetype not in ('audio/wav', 'audio/x-wav'):
            ffmpeg = self._ai_ffmpeg()
            if not ffmpeg:
                _logger.info('Meta solo transcribe WAV y no hay ffmpeg para convertir el audio: configura '
                             'un proveedor de audio en Ajustes o instala ffmpeg.')
                return ''
            raw = to_wav(raw, ffmpeg)
        model = self.env['ir.config_parameter'].sudo().get_param('chatroom_ai.meta_transcription_model') \
            or META_ASR_MODEL
        settings = {'model': model, 'audioEncoding': 'WAV', 'mode': 'PUSH_TO_TALK', 'languageBias': ['Spanish']}
        response = requests.post(
            '%s/asr/transcribe' % base,
            headers={'Authorization': 'Bearer %s' % key, 'Accept': 'application/json'},
            files={'request': (None, json.dumps(settings), 'application/json'),
                   'audio': ('audio.wav', raw, 'audio/wav')}, timeout=90)
        response.raise_for_status()
        return (response.json() or {}).get('transcript') or ''

    def _ai_describe_image(self, attachment, caption=''):
        raw = attachment.raw
        mimetype = (attachment.mimetype or '').split(';')[0].strip()
        if not raw or len(raw) > IMAGE_LIMIT or not mimetype.startswith('image/'):
            return ''
        data_uri = 'data:%s;base64,%s' % (mimetype, base64.b64encode(raw).decode())
        return self._ai_chat_completion([
            {'role': 'system', 'content': _(
                'Describe en una o dos frases, en español, lo que muestra la imagen que un cliente envió por '
                'WhatsApp, pensando en atenderlo: producto, texto o números visibles, daños, comprobantes de '
                'pago, capturas de pantalla. No inventes lo que no se ve.')},
            {'role': 'user', 'content': [
                {'type': 'text', 'text': caption or _('Imagen enviada por el cliente.')},
                {'type': 'image_url', 'image_url': {'url': data_uri}},
            ]},
        ], task_type='summary')

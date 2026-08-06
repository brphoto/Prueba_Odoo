# -*- coding: utf-8 -*-
"""Webhook propio para la API oficial de WhatsApp Business (Meta Cloud API).

No se usa ningún proveedor externo (Twilio, Chat-API, Wassenger, etc.): las
notificaciones llegan directo desde los servidores de Meta a esta URL, y las
respuestas se envían directo a graph.facebook.com (ver chatroom_channel.py).
"""
import hashlib
import hmac
import logging

from odoo import fields, http
from odoo.http import request

_logger = logging.getLogger(__name__)


class WhatsAppWebhookController(http.Controller):

    @http.route('/chatroom_whatsapp/webhook', type='http', auth='public',
                methods=['GET'], csrf=False)
    def whatsapp_webhook_verify(self, **kwargs):
        """Verificación inicial del webhook exigida por Meta."""
        verify_token = request.env['ir.config_parameter'].sudo().get_param(
            'chatroom_whatsapp.webhook_verify_token')
        mode = kwargs.get('hub.mode')
        token = kwargs.get('hub.verify_token')
        challenge = kwargs.get('hub.challenge')

        if mode == 'subscribe' and verify_token and token == verify_token:
            return request.make_response(challenge or '')
        _logger.warning("Fallo de verificación del webhook de WhatsApp")
        return request.make_response('Forbidden', status=403)

    @http.route('/chatroom_whatsapp/webhook', type='http', auth='public',
                methods=['POST'], csrf=False)
    def whatsapp_webhook_receive(self, **kwargs):
        """Recibe mensajes entrantes y actualizaciones de estado."""
        raw_body = request.httprequest.get_data()
        if not self._is_valid_signature(raw_body):
            _logger.warning("Firma inválida en webhook de WhatsApp, se descarta")
            return request.make_response('Forbidden', status=403)

        payload = request.get_json_data() or {}
        env = request.env(su=True)

        for entry in payload.get('entry', []):
            for change in entry.get('changes', []):
                value = change.get('value', {})
                self._process_statuses(env, value.get('statuses', []))
                self._process_messages(env, value)

        return request.make_response('EVENT_RECEIVED')

    # ------------------------------------------------------------------
    def _is_valid_signature(self, raw_body):
        app_secret = request.env['ir.config_parameter'].sudo().get_param(
            'chatroom_whatsapp.app_secret')
        if not app_secret:
            # Sin App Secret configurado no se puede verificar; se permite
            # pasar para no romper instalaciones en curso, pero se
            # recomienda configurarlo en producción.
            return True

        signature = request.httprequest.headers.get('X-Hub-Signature-256', '')
        expected = 'sha256=' + hmac.new(
            app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)

    def _process_messages(self, env, value):
        contacts = {c['wa_id']: c.get('profile', {}).get('name')
                    for c in value.get('contacts', [])}

        for msg in value.get('messages', []):
            wa_id = msg.get('from')
            profile_name = contacts.get(wa_id)
            channel = env['chatroom.channel']._find_or_create_from_webhook(
                'whatsapp', wa_id, profile_name)

            msg_type = msg.get('type', 'text')
            body, media_id = self._extract_body(msg, msg_type)

            message = env['chatroom.message'].create({
                'channel_id': channel.id,
                'direction': 'inbound',
                'message_type': msg_type if msg_type in dict(
                    env['chatroom.message']._fields['message_type'].selection
                ) else 'other',
                'body': body,
                'wa_message_id': msg.get('id'),
                'state': 'received',
            })
            if media_id:
                message._fetch_whatsapp_media(media_id)

            channel.write({
                'last_message_date': fields.Datetime.now(),
                'state': 'pending',
            })
            channel._ai_process_inbound_message(message)
            channel._notify_assigned_agent(message)
            channel._notify_thread_update()

    def _process_statuses(self, env, statuses):
        state_map = {
            'sent': 'sent', 'delivered': 'delivered',
            'read': 'read', 'failed': 'failed',
        }
        for status in statuses:
            message = env['chatroom.message'].search(
                [('wa_message_id', '=', status.get('id'))], limit=1)
            new_state = state_map.get(status.get('status'))
            if message and new_state:
                message.write({'state': new_state})

    @staticmethod
    def _extract_body(msg, msg_type):
        if msg_type == 'text':
            return msg.get('text', {}).get('body'), False
        if msg_type in ('image', 'audio', 'video', 'document'):
            media = msg.get(msg_type, {})
            return media.get('caption'), media.get('id')
        if msg_type == 'button':
            return msg.get('button', {}).get('text'), False
        if msg_type == 'interactive':
            interactive = msg.get('interactive', {})
            reply = interactive.get('button_reply') or interactive.get('list_reply') or {}
            return reply.get('title'), False
        return None, False

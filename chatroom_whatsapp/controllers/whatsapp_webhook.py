# -*- coding: utf-8 -*-
"""Webhook propio para la API oficial de WhatsApp Business (Meta Cloud API).

No se usa ningún proveedor externo (Twilio, Chat-API, Wassenger, etc.): las
notificaciones llegan directo desde los servidores de Meta a esta URL, y las
respuestas se envían directo a graph.facebook.com (ver chatroom_channel.py).
"""
import hashlib
import hmac
import json
import logging

from psycopg2 import IntegrityError

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
        """Recibe eventos de WhatsApp, Messenger e Instagram: los tres
        productos de Meta pueden compartir la misma App y el mismo
        webhook; 'object' en el payload indica cuál es."""
        raw_body = request.httprequest.get_data()
        max_bytes = request.env['ir.config_parameter'].sudo().get_param(
            'chatroom_whatsapp.webhook_max_bytes', '2097152')
        try:
            max_bytes = max(65536, min(int(max_bytes), 10485760))
        except (TypeError, ValueError):
            max_bytes = 2097152
        if len(raw_body) > max_bytes:
            _logger.warning('Payload de webhook demasiado grande: %s bytes', len(raw_body))
            return request.make_response('Payload Too Large', status=413)
        if not self._is_valid_signature(raw_body):
            _logger.warning("Firma inválida en webhook de WhatsApp, se descarta")
            return request.make_response('Forbidden', status=403)

        payload = request.get_json_data() or {}
        if not isinstance(payload, dict):
            return request.make_response('Bad Request', status=400)
        object_type = payload.get('object')
        env = request.env(su=True)
        # Timestamp de salud: "llegó algo del webhook", más allá de si el
        # evento en sí se termina procesando o descartando por duplicado.
        env['ir.config_parameter'].set_param(
            'chatroom_whatsapp.last_webhook_at', fields.Datetime.now())

        event = env['chatroom.whatsapp.webhook.event'].create({
            'name': 'Webhook %s' % (object_type or 'desconocido'),
            'object_type': object_type or False,
            'payload_json': json.dumps(payload, ensure_ascii=False),
        })

        # El camino normal es sincrónico: Meta recibe la respuesta después de
        # que el mensaje ya fue creado, asociado a su conversación y publicado
        # por bus para que el agente lo vea sin recargar la pantalla.
        event.write({
            'state': 'running',
            'attempts': 1,
            'error_message': False,
        })
        try:
            with env.cr.savepoint():
                self.process_payload(env, payload)
            event.write({
                'state': 'done',
                'processed_at': fields.Datetime.now(),
                'error_message': False,
                'payload_json': '{}',
            })
        except Exception as error:  # noqa: BLE001 - el cron queda como respaldo
            # Meta debe recibir 200 para no generar reintentos duplicados. El
            # payload queda conservado y el cron solo recupera este caso.
            _logger.exception(
                'Falló el procesamiento directo del evento de webhook %s',
                event.id)
            event.write({
                'state': 'pending',
                'next_attempt_at': fields.Datetime.now(),
                'error_message': str(error)[:4000],
            })

        return request.make_response('EVENT_RECEIVED')

    def process_payload(self, env, payload):
        """Procesa un payload encolado fuera de la petición HTTP pública."""
        object_type = payload.get('object')
        for entry in payload.get('entry', []):
            if object_type == 'whatsapp_business_account':
                for change in entry.get('changes', []):
                    value = change.get('value', {})
                    self._process_statuses(env, value.get('statuses', []))
                    self._process_messages(env, value)
            elif object_type in ('page', 'instagram'):
                channel_type = 'instagram' if object_type == 'instagram' else 'messenger'
                for messaging_event in entry.get('messaging', []):
                    self._process_messenger_event(env, channel_type, messaging_event)

    # ------------------------------------------------------------------
    def _is_valid_signature(self, raw_body):
        app_secret = request.env['ir.config_parameter'].sudo().get_param(
            'chatroom_whatsapp.app_secret')
        if not app_secret:
            # Sin App Secret configurado no hay forma de verificar que el
            # POST venga realmente de Meta: el endpoint es auth='public',
            # así que dejar pasar acá equivale a aceptar mensajes,
            # contactos y confirmaciones de estado falsificados de
            # cualquiera que conozca la URL. Se rechaza en vez de permitir.
            _logger.warning(
                "Webhook de WhatsApp sin App Secret configurado: se rechaza "
                "el POST (configuralo en el asistente de conexión)")
            return False

        signature = request.httprequest.headers.get('X-Hub-Signature-256', '')
        expected = 'sha256=' + hmac.new(
            app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)

    @staticmethod
    def _already_processed(env, wa_message_id):
        """Meta garantiza entrega 'al menos una vez': ante un timeout o un
        5xx nuestro, reintenta el mismo evento. Sin esta comprobación se
        duplicarían mensajes, contactos, notificaciones y respuestas de
        IA por cada reintento."""
        if not wa_message_id:
            return False
        exists = bool(env['chatroom.message'].search_count(
            [('wa_message_id', '=', wa_message_id)], limit=1))
        if exists:
            _logger.info(
                "Evento %s ya procesado, se omite (reintento de Meta)", wa_message_id)
        return exists

    @staticmethod
    def _create_inbound_message(env, values):
        """Crea un mensaje entrante y tolera carreras entre reintentos.

        La búsqueda previa evita la mayoría de duplicados, pero dos workers
        pueden consultar al mismo tiempo antes de que alguno confirme su
        transacción. La restricción única de ``wa_message_id`` es la última
        barrera; si la activa otro worker, este evento ya quedó atendido.
        """
        try:
            with env.cr.savepoint():
                return env['chatroom.message'].create(values)
        except IntegrityError:
            if values.get('wa_message_id') and WhatsAppWebhookController._already_processed(
                    env, values['wa_message_id']):
                _logger.info(
                    "Carrera controlada: el mensaje %s ya fue creado por otro worker",
                    values['wa_message_id'])
                return env['chatroom.message'].browse()
            raise

    def _process_messages(self, env, value):
        contacts = {c['wa_id']: c.get('profile', {}).get('name')
                    for c in value.get('contacts', [])}
        # Cuando hay varias líneas de WhatsApp dadas de alta, Meta indica
        # por cuál entró el mensaje en 'metadata.phone_number_id'.
        meta_phone_number_id = (value.get('metadata') or {}).get('phone_number_id')

        for msg in value.get('messages', []):
            if self._already_processed(env, msg.get('id')):
                continue

            wa_id = msg.get('from')
            profile_name = contacts.get(wa_id)
            channel = env['chatroom.channel']._find_or_create_from_webhook(
                'whatsapp', wa_id, profile_name, meta_phone_number_id=meta_phone_number_id)

            msg_type = msg.get('type', 'text')

            if msg_type == 'reaction':
                # Una reacción no es un mensaje nuevo: se pega al mensaje
                # citado (o se borra, si viene sin emoji), igual que en la
                # app de WhatsApp.
                self._process_reaction(env, channel, msg)
                continue

            body, media_id = self._extract_body(msg, msg_type)

            context_id = (msg.get('context') or {}).get('id')
            reply_to = env['chatroom.message'].search(
                [('wa_message_id', '=', context_id)], limit=1) if context_id else None

            message = self._create_inbound_message(env, {
                'channel_id': channel.id,
                'direction': 'inbound',
                'message_type': msg_type if msg_type in dict(
                    env['chatroom.message']._fields['message_type'].selection
                ) else 'other',
                'body': body,
                'wa_message_id': msg.get('id'),
                'reply_to_id': reply_to.id if reply_to else False,
                'state': 'received',
            })
            if not message:
                continue
            if media_id:
                message._fetch_whatsapp_media(media_id)
            channel._handle_interactive_reply(msg_type, msg)

            channel.write({
                'last_message_date': fields.Datetime.now(),
                'state': 'pending',
            })
            channel._handle_opt_keywords(message)
            if not channel._maybe_send_away_message():
                channel._ai_process_inbound_message(message)
            channel._notify_assigned_agent(message)
            channel._notify_thread_update()
            channel._notify_new_inbound_message(message)

    def _process_reaction(self, env, channel, msg):
        reaction = msg.get('reaction') or {}
        target_wa_id = reaction.get('message_id')
        emoji = reaction.get('emoji') or False
        target = env['chatroom.message'].search(
            [('wa_message_id', '=', target_wa_id)], limit=1)
        if not target:
            return
        target.write({'partner_reaction': emoji})
        channel._notify_thread_update()

    def _process_messenger_event(self, env, channel_type, event):
        """Mensaje entrante de Messenger o Instagram Direct (mismo Send
        API de Meta, payload distinto al de WhatsApp)."""
        sender_id = (event.get('sender') or {}).get('id')
        message_data = event.get('message')
        if not sender_id or not message_data or message_data.get('is_echo'):
            # is_echo = eco del propio mensaje que el negocio envió
            return
        if self._already_processed(env, message_data.get('mid')):
            return

        channel = env['chatroom.channel']._find_or_create_from_webhook(channel_type, sender_id)
        body = message_data.get('text')
        attachments = message_data.get('attachments') or []
        message_type = 'text'
        if not body and attachments:
            message_type = {
                'image': 'image', 'video': 'video', 'audio': 'audio', 'file': 'document',
            }.get(attachments[0].get('type'), 'other')

        message = self._create_inbound_message(env, {
            'channel_id': channel.id,
            'direction': 'inbound',
            'message_type': message_type,
            'body': body,
            'wa_message_id': message_data.get('mid'),
            'state': 'received',
        })
        if not message:
            return
        for attachment in attachments:
            url = (attachment.get('payload') or {}).get('url')
            if url:
                message._fetch_generic_attachment(url)

        channel.write({
            'last_message_date': fields.Datetime.now(),
            'state': 'pending',
        })
        channel._handle_opt_keywords(message)
        if not channel._maybe_send_away_message():
            channel._ai_process_inbound_message(message)
        channel._notify_assigned_agent(message)
        channel._notify_thread_update()
        channel._notify_new_inbound_message(message)

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
        if msg_type == 'location':
            location = msg.get('location', {})
            lat, lng = location.get('latitude'), location.get('longitude')
            lines = [line for line in (location.get('name'), location.get('address')) if line]
            if lat is not None and lng is not None:
                lines.append(f"https://www.google.com/maps?q={lat},{lng}")
            return "\n".join(lines) or None, False
        return None, False

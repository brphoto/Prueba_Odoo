# -*- coding: utf-8 -*-
import base64
import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ChatroomMessage(models.Model):
    _name = 'chatroom.message'
    _description = "Mensaje de Chatroom (WhatsApp / Redes Sociales)"
    _order = 'date asc, id asc'

    display_name = fields.Char(compute='_compute_display_name')
    channel_id = fields.Many2one(
        'chatroom.channel', string="Conversación", required=True,
        ondelete='cascade', index=True)
    direction = fields.Selection(
        [('inbound', "Entrante"), ('outbound', "Saliente")],
        required=True)
    message_type = fields.Selection(
        [('text', "Texto"),
         ('image', "Imagen"),
         ('document', "Documento"),
         ('audio', "Audio"),
         ('video', "Video"),
         ('template', "Plantilla"),
         ('interactive', "Botones/lista"),
         ('location', "Ubicación"),
         ('other', "Otro")],
        default='text', required=True)
    body = fields.Text()
    attachment_ids = fields.Many2many(
        'ir.attachment', 'chatroom_message_ir_attachments_rel',
        'message_id', 'attachment_id', string="Adjuntos")
    wa_message_id = fields.Char(string="ID de mensaje (Meta)", index=True, copy=False)
    reply_to_id = fields.Many2one(
        'chatroom.message', string="Respuesta a", ondelete='set null',
        help="Mensaje citado, cuando el cliente responde a un mensaje "
             "específico desde WhatsApp.")
    state = fields.Selection(
        [('received', "Recibido"),
         ('pending', "Enviando"),
         ('sent', "Enviado"),
         ('delivered', "Entregado"),
         ('read', "Leído"),
         ('failed', "Fallido")],
        default='received')
    date = fields.Datetime(default=fields.Datetime.now, required=True)
    retry_count = fields.Integer(
        default=0, copy=False,
        help="Cuántas veces se reintentó el envío (a mano o automático). "
             "El cron de reintentos deja de intentar después de 3.")
    sender_user_id = fields.Many2one(
        'res.users', string="Enviado por", copy=False,
        help="Agente que escribió este mensaje saliente. Vacío en "
             "mensajes entrantes y en los que mandó la automatización de "
             "IA (corren con el usuario del webhook, no de una persona).")
    own_reaction = fields.Char(
        copy=False,
        help="Emoji con el que reaccionamos nosotros a este mensaje "
             "(estilo WhatsApp: la reacción se pega al mensaje, no genera "
             "un mensaje nuevo).")
    partner_reaction = fields.Char(
        copy=False,
        help="Emoji con el que reaccionó el contacto a este mensaje, "
             "recibido por webhook.")

    @api.depends('body')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = (rec.body or '')[:60]

    def action_ai_translate(self):
        """Traduce este mensaje al idioma del usuario actual usando el
        mismo proveedor de IA configurado para sugerencias/resúmenes.
        No persiste la traducción: se devuelve al widget para mostrarla
        en línea bajo el mensaje original."""
        self.ensure_one()
        if not self.body:
            return ''
        target_lang = self.env.user.lang or 'es_ES'
        system_prompt = _(
            "Traduce el siguiente mensaje de WhatsApp al idioma con "
            "código '%s'. Responde ÚNICAMENTE con la traducción, sin "
            "comillas ni explicaciones adicionales.") % target_lang
        try:
            return self.channel_id._ai_chat_completion([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": self.body},
            ])
        except (requests.RequestException, KeyError, IndexError) as exc:
            _logger.error("Error consultando IA para traducción: %s", exc)
            raise UserError(_("No se pudo traducir el mensaje: %s") % exc)

    def _fetch_whatsapp_media(self, media_id):
        """Descarga un adjunto entrante desde Meta y lo guarda como
        ir.attachment. Las URLs de media de Meta expiran en minutos, por
        lo que se descarga inmediatamente al recibir el webhook."""
        self.ensure_one()
        token, _phone_number_id, api_version = self.channel_id._get_meta_credentials()
        headers = {"Authorization": f"Bearer {token}"}
        try:
            meta_resp = self.channel_id._meta_request(
                'GET', f"https://graph.facebook.com/{api_version}/{media_id}",
                headers=headers, timeout=15)
            meta_resp.raise_for_status()
            media_info = meta_resp.json()
            file_resp = self.channel_id._meta_request(
                'GET', media_info['url'], headers=headers, timeout=30)
            file_resp.raise_for_status()
        except requests.RequestException as exc:
            _logger.error("No se pudo descargar el adjunto de WhatsApp %s: %s", media_id, exc)
            return

        attachment = self.env['ir.attachment'].create({
            'name': media_id,
            'mimetype': media_info.get('mime_type'),
            'datas': base64.b64encode(file_resp.content),
        })
        self.attachment_ids = [(4, attachment.id)]

    def _fetch_generic_attachment(self, url):
        """Descarga un adjunto entrante de Messenger/Instagram: a
        diferencia de WhatsApp, esas URLs son públicas y no requieren el
        token en el header."""
        self.ensure_one()
        try:
            response = self.channel_id._meta_request('GET', url, timeout=30)
            response.raise_for_status()
        except requests.RequestException as exc:
            _logger.error("No se pudo descargar el adjunto %s: %s", url, exc)
            return

        name = (url.split('?')[0].rstrip('/').split('/')[-1]) or 'archivo'
        attachment = self.env['ir.attachment'].create({
            'name': name,
            'mimetype': response.headers.get('Content-Type', 'application/octet-stream'),
            'datas': base64.b64encode(response.content),
        })
        self.attachment_ids = [(4, attachment.id)]

# -*- coding: utf-8 -*-
import base64
import logging

import requests

from odoo import api, fields, models

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
         ('other', "Otro")],
        default='text', required=True)
    body = fields.Text()
    attachment_ids = fields.Many2many(
        'ir.attachment', 'chatroom_message_ir_attachments_rel',
        'message_id', 'attachment_id', string="Adjuntos")
    wa_message_id = fields.Char(string="ID de mensaje (Meta)", index=True, copy=False)
    state = fields.Selection(
        [('received', "Recibido"),
         ('sent', "Enviado"),
         ('delivered', "Entregado"),
         ('read', "Leído"),
         ('failed', "Fallido")],
        default='received')
    date = fields.Datetime(default=fields.Datetime.now, required=True)

    @api.depends('body')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = (rec.body or '')[:60]

    def _fetch_whatsapp_media(self, media_id):
        """Descarga un adjunto entrante desde Meta y lo guarda como
        ir.attachment. Las URLs de media de Meta expiran en minutos, por
        lo que se descarga inmediatamente al recibir el webhook."""
        self.ensure_one()
        token, _phone_number_id, api_version = self.channel_id._get_meta_credentials()
        headers = {"Authorization": f"Bearer {token}"}
        try:
            meta_resp = requests.get(
                f"https://graph.facebook.com/{api_version}/{media_id}",
                headers=headers, timeout=15)
            meta_resp.raise_for_status()
            media_info = meta_resp.json()
            file_resp = requests.get(media_info['url'], headers=headers, timeout=30)
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

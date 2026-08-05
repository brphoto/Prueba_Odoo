# -*- coding: utf-8 -*-
from odoo import api, fields, models


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
    attachment_url = fields.Char()
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

# -*- coding: utf-8 -*-
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    whatsapp_id = fields.Char(
        string="WhatsApp ID (wa_id)", copy=False,
        help="Número en formato internacional tal como lo entrega Meta "
             "(sin '+', sin espacios). Se completa automáticamente al "
             "recibir el primer mensaje.")
    whatsapp_opt_out = fields.Boolean(
        string="Dado de baja de WhatsApp", copy=False, tracking=True,
        help="El contacto pidió no recibir más mensajes (escribió una "
             "palabra clave de baja, o se marcó manualmente aquí). "
             "Mientras esté activo, el chatroom bloquea el envío de "
             "mensajes a este contacto.")
    whatsapp_opt_out_date = fields.Datetime(
        string="Fecha de baja", copy=False, readonly=True)
    chatroom_channel_ids = fields.One2many(
        'chatroom.channel', 'partner_id', string="Conversaciones")
    chatroom_channel_count = fields.Integer(
        compute='_compute_chatroom_channel_count')

    def _compute_chatroom_channel_count(self):
        grouped = self.env['chatroom.channel']._read_group(
            [('partner_id', 'in', self.ids)], ['partner_id'], ['__count'])
        counts = {partner.id: count for partner, count in grouped}
        for rec in self:
            rec.chatroom_channel_count = counts.get(rec.id, 0)

    def action_view_chatroom_channels(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': "Conversaciones",
            'res_model': 'chatroom.channel',
            'view_mode': 'list,form',
            'domain': [('partner_id', '=', self.id)],
            'context': {'default_partner_id': self.id},
        }

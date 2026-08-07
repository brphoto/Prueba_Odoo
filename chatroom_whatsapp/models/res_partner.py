# -*- coding: utf-8 -*-
import re

from odoo import api, fields, models

DIGITS_RE = re.compile(r'\D')


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

    @api.model
    def _find_by_whatsapp_number(self, wa_id):
        """Busca un contacto existente por teléfono comparando solo
        dígitos, antes de crear uno nuevo. Evita duplicar contactos que
        ya existían en Odoo (importados, creados a mano, de otra
        integración) con el mismo número pero sin whatsapp_id todavía.

        Nota: en Odoo 19 'mobile' ya no es un campo aparte de res.partner
        (se unificó con 'phone'), así que solo se compara ese campo."""
        digits = DIGITS_RE.sub('', wa_id or '')
        if len(digits) < 8:
            return self.browse()
        tail = digits[-8:]
        # No se puede filtrar por "like" a nivel SQL: los teléfonos suelen
        # guardarse con espacios/guiones ("+57 300 123 4567"), así que la
        # cola de dígitos no aparece como substring literal. Se compara en
        # Python sobre los contactos que sí tienen algún teléfono cargado.
        candidates = self.search([('phone', '!=', False)])
        for partner in candidates:
            if partner.phone and DIGITS_RE.sub('', partner.phone)[-8:] == tail:
                return partner
        return self.browse()

    def action_view_chatroom_channels(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': "Conversaciones",
            'res_model': 'chatroom.channel',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [('partner_id', '=', self.id)],
            'context': {'default_partner_id': self.id},
        }

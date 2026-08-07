# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ChatroomNewConversationWizard(models.TransientModel):
    _name = 'chatroom.new.conversation.wizard'
    _description = "Nueva conversación de WhatsApp"

    partner_id = fields.Many2one(
        'res.partner', string="Contacto", required=True,
        help="Elegí un contacto existente o escribí un nombre nuevo para "
             "crearlo al vuelo.")
    phone = fields.Char(
        string="Número de WhatsApp",
        help="Con código de país. Si lo dejás vacío se usa el teléfono "
             "del contacto.")
    whatsapp_number_id = fields.Many2one(
        'chatroom.whatsapp.number', string="Línea de WhatsApp")

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.partner_id:
            self.phone = self.partner_id.phone

    def action_confirm(self):
        self.ensure_one()
        channel_id = self.env['chatroom.channel'].action_start_conversation(
            self.partner_id.id, self.phone, self.whatsapp_number_id.id)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'chatroom.channel',
            'res_id': channel_id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }

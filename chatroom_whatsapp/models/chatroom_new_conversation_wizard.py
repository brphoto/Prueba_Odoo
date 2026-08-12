# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ChatroomNewConversationWizard(models.TransientModel):
    _name = 'chatroom.new.conversation.wizard'
    _description = "Nueva conversación de WhatsApp"

    partner_id = fields.Many2one(
        'res.partner', string="Contacto",
        help="Elegí un contacto existente o escribí un nombre nuevo para "
             "crearlo al vuelo.")
    phone = fields.Char(
        string="Número de WhatsApp",
        help="Con código de país. Si lo dejás vacío se usa el teléfono "
             "del contacto.")
    whatsapp_number_id = fields.Many2one(
        'chatroom.whatsapp.number', string="Línea de WhatsApp")
    contact_name = fields.Char(string="Nombre del nuevo contacto")
    contact_email = fields.Char(string="Email")
    lead_name = fields.Char(string="Nombre de oportunidad")
    expected_revenue = fields.Float(string="Ingreso esperado")
    product_id = fields.Many2one('product.product', string="Producto del presupuesto")
    product_qty = fields.Float(string="Cantidad", default=1.0)

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.partner_id:
            self.phone = self.partner_id.phone

    def action_confirm(self):
        self.ensure_one()
        if not self.partner_id:
            if not self.contact_name or not self.phone:
                raise UserError(_('Indica nombre y teléfono para crear el contacto.'))
            self.partner_id = self.env['res.partner'].create({
                'name': self.contact_name, 'phone': self.phone, 'email': self.contact_email,
            })
        elif self.contact_email and not self.partner_id.email:
            self.partner_id.email = self.contact_email
        channel_id = self.env['chatroom.channel'].action_start_conversation(
            self.partner_id.id, self.phone, self.whatsapp_number_id.id)
        channel = self.env['chatroom.channel'].browse(channel_id)
        if self.lead_name and 'crm.lead' in self.env:
            lead = self.env['crm.lead'].create({
                'name': self.lead_name, 'partner_id': self.partner_id.id,
                'expected_revenue': self.expected_revenue,
                'user_id': self.env.user.id,
            })
            channel.pinned_lead_id = lead.id
        if self.product_id and 'sale.order' in self.env:
            order = self.env['sale.order'].create({
                'partner_id': self.partner_id.id,
                'origin': channel.display_name,
                'order_line': [(0, 0, {
                    'product_id': self.product_id.id,
                    'product_uom_qty': max(1.0, self.product_qty),
                })],
            })
            channel.message_post(body=_('Presupuesto %s creado desde el onboarding rápido.') % order.name)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'chatroom.channel',
            'res_id': channel_id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
        }

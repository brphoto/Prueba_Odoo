# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError


class ChatroomSendCatalogWizard(models.TransientModel):
    _name = 'chatroom.send.catalog.wizard'
    _description = "Enviar catálogo de productos por WhatsApp"

    channel_id = fields.Many2one('chatroom.channel', required=True)
    product_ids = fields.Many2many(
        'product.product', string="Productos",
        domain=[('sale_ok', '=', True)],
        help="Hasta 10 productos: es el máximo que permite un mensaje de "
             "lista interactiva de WhatsApp.")

    def action_send(self):
        self.ensure_one()
        if not self.product_ids:
            raise UserError(_("Elegí al menos un producto."))
        if len(self.product_ids) > 10:
            raise UserError(_("Elegí como máximo 10 productos por mensaje."))
        self.channel_id.action_send_product_catalog(self.product_ids.ids)
        return {'type': 'ir.actions.act_window_close'}

# -*- coding: utf-8 -*-
from odoo import fields, models


class ChatroomCartLine(models.Model):
    """Línea de un carrito que la IA (o un agente) fue armando charlando
    con el cliente por WhatsApp, antes de convertirlo en una Cotización
    real de Ventas.

    'product_id' se guarda como Integer (no Many2one a product.product)
    a propósito: 'product'/'sale' son módulos opcionales que este módulo
    no declara en 'depends', y un Many2one a un modelo no instalado
    rompe la carga completa del registro (el mismo problema que ya
    resolvió 'pinned_lead_id' en chatroom.channel para crm.lead)."""
    _name = 'chatroom.cart.line'
    _description = "Línea de carrito de Chatroom"
    _order = 'id'

    channel_id = fields.Many2one(
        'chatroom.channel', string="Conversación", required=True,
        ondelete='cascade', index=True)
    product_id = fields.Integer(string="ID de producto", required=True)
    product_name = fields.Char(required=True)
    quantity = fields.Float(default=1.0, required=True)
    price_unit = fields.Float(
        string="Precio (referencia)",
        help="Precio del producto al momento de agregarlo al carrito. "
             "Solo informativo: el precio real de la cotización lo "
             "recalcula Ventas al crearla.")

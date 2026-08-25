# -*- coding: utf-8 -*-
from odoo import fields, models


class ChatroomAiSalesEvent(models.Model):
    _inherit = 'chatroom.ai.sales.event'

    event = fields.Selection(selection_add=[
        ('delivery_ready', 'Entrega preparada'),
        ('delivery_done', 'Entrega completada'),
        ('delivery_cancelled', 'Entrega cancelada'),
        ('cart_reminder', 'Recordatorio de carrito'),
        ('payment_retry', 'Reintento de pago'),
    ], ondelete={
        # El campo base es obligatorio y no tiene valor por defecto; al
        # desinstalar esta capa se eliminan únicamente sus eventos propios.
        'delivery_ready': 'cascade',
        'delivery_done': 'cascade',
        'delivery_cancelled': 'cascade',
        'cart_reminder': 'cascade',
        'payment_retry': 'cascade',
    })

# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    chatroom_ai_sales_require_stock = fields.Boolean(
        string='Validar inventario antes de confirmar',
        config_parameter='chatroom_ai_sales.require_stock',
        help='Bloquea la confirmación autónoma de productos físicos que no tengan disponibilidad suficiente.',
    )
    chatroom_ai_sales_require_delivery_address = fields.Boolean(
        string='Exigir dirección de entrega completa',
        config_parameter='chatroom_ai_sales.require_delivery_address',
        help='Exige calle, ciudad y país en la dirección de entrega antes de una confirmación automática.',
    )
    chatroom_ai_sales_notify_delivery = fields.Boolean(
        string='Notificar avances de entrega por WhatsApp',
        default=True,
        config_parameter='chatroom_ai_sales.notify_delivery',
        help='Informa cuando el pedido está listo, entregado o cancelado.',
    )
    chatroom_ai_sales_cart_reminder_enabled = fields.Boolean(
        string='Recordar carritos abandonados',
        config_parameter='chatroom_ai_sales.cart_reminder_enabled',
        help='Envía como máximo el número configurado de recordatorios por carrito.',
    )
    chatroom_ai_sales_cart_reminder_hours = fields.Integer(
        string='Horas para considerar abandonado un carrito',
        default=24,
        config_parameter='chatroom_ai_sales.cart_reminder_hours',
    )
    chatroom_ai_sales_cart_reminder_max = fields.Integer(
        string='Máximo de recordatorios por carrito',
        default=1,
        config_parameter='chatroom_ai_sales.cart_reminder_max',
    )
    chatroom_ai_sales_payment_retry_enabled = fields.Boolean(
        string='Reintentar enlaces de pago fallidos',
        config_parameter='chatroom_ai_sales.payment_retry_enabled',
        help='Reenvía automáticamente solo enlaces fallidos dentro del límite de intentos configurado.',
    )
    chatroom_ai_sales_payment_retry_hours = fields.Integer(
        string='Horas antes de reintentar un pago',
        default=24,
        config_parameter='chatroom_ai_sales.payment_retry_hours',
    )
    chatroom_ai_sales_payment_retry_max = fields.Integer(
        string='Máximo de reintentos de pago',
        default=1,
        config_parameter='chatroom_ai_sales.payment_retry_max',
    )

# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    chatroom_ai_sales_auto_create_invoice = fields.Boolean(
        string='Preparar factura al recibir el pago',
        config_parameter='chatroom_ai_sales.auto_create_invoice',
        help='Genera una factura borrador para el pedido pagado, sin publicarla automáticamente.',
    )
    chatroom_ai_sales_auto_post_invoice = fields.Boolean(
        string='Publicar factura automáticamente',
        config_parameter='chatroom_ai_sales.auto_post_invoice',
        help='Publica la factura después del pago. Actívalo solo si la fiscalización automática está validada.',
    )
    chatroom_ai_sales_notify_payment = fields.Boolean(
        string='Notificar pago recibido por WhatsApp',
        default=True,
        config_parameter='chatroom_ai_sales.notify_payment',
        help='Envía confirmación al cliente y deja el resultado auditado. Fuera de la ventana de WhatsApp puede requerir plantilla aprobada.',
    )

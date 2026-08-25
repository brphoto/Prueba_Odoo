# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    chatroom_ai_sales_enabled = fields.Boolean(
        string='Activar ventas autónomas por WhatsApp',
        config_parameter='chatroom_ai_sales.enabled',
        help='Permite que el vendedor automático procese carritos y prepare ventas desde WhatsApp.',
    )
    chatroom_ai_sales_auto_confirm = fields.Boolean(
        string='Confirmar pedidos automáticamente',
        config_parameter='chatroom_ai_sales.auto_confirm',
        help='Confirma únicamente después de una confirmación explícita del cliente y si se cumplen todos los límites.',
    )
    chatroom_ai_sales_max_auto_amount = fields.Float(
        string='Monto máximo de confirmación automática',
        config_parameter='chatroom_ai_sales.max_auto_amount',
        help='Debe ser mayor que cero para confirmar pedidos automáticamente. Usa la moneda de la compañía.',
    )
    chatroom_ai_sales_auto_payment_link = fields.Boolean(
        string='Enviar link de pago después de confirmar',
        config_parameter='chatroom_ai_sales.auto_payment_link',
        help='Usa el proveedor de pagos instalado, incluido PayPhone si está configurado. Si falla, escala al equipo.',
    )

    def set_values(self):
        result = super().set_values()
        if self.chatroom_ai_sales_enabled:
            # Activar la capa comercial también prepara el motor de carrito
            # existente. No desactiva preferencias previas al apagarla.
            icp = self.env['ir.config_parameter'].sudo()
            icp.set_param('chatroom_whatsapp.ai_enabled', 'True')
            icp.set_param('chatroom_whatsapp.ai_auto_order_reply', 'True')
        return result

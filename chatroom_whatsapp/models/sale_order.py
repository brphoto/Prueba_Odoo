# -*- coding: utf-8 -*-
import logging

from odoo import models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_confirm(self):
        res = super().action_confirm()
        self._chatroom_notify_order_confirmed()
        return res

    def _chatroom_notify_order_confirmed(self):
        """Aviso automático por WhatsApp cuando se confirma un
        presupuesto (pasa a Pedido de venta), si hay una plantilla
        configurada en Ajustes > Chatroom WhatsApp. Dos decisiones de
        diseño a propósito:

        - Usa una PLANTILLA aprobada por Meta, no texto libre: una
          notificación disparada por un evento de Odoo casi siempre le
          va a llegar a alguien fuera de la ventana de 24h, y Meta
          rechaza texto libre en ese caso.
        - Solo se manda si el contacto YA tiene una conversación de
          WhatsApp (no crea una nueva): auto-armar una conversación y
          mandarle una plantilla a cualquier cliente con teléfono
          cargado, así nunca haya usado WhatsApp con este negocio, es
          justo el tipo de ruido que se quiere evitar."""
        icp = self.env['ir.config_parameter'].sudo()
        template_id = icp.get_param('chatroom_whatsapp.notify_order_confirmed_template_id')
        if not template_id:
            return
        template = self.env['chatroom.template'].browse(int(template_id)).exists()
        if not template:
            return
        Channel = self.env['chatroom.channel']
        for order in self:
            if not order.partner_id:
                continue
            channel = Channel.search([
                ('partner_id', '=', order.partner_id.id),
                ('channel_type', '=', 'whatsapp'),
            ], order='last_message_date desc', limit=1)
            if not channel:
                continue
            try:
                channel.action_send_template(
                    template.name, template.language, template.get_variable_values(channel))
            except UserError as exc:
                _logger.info(
                    "No se pudo mandar el aviso de pedido confirmado por WhatsApp "
                    "(pedido %s): %s", order.name, exc)

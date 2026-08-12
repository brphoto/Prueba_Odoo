# -*- coding: utf-8 -*-
import logging

from odoo import models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    def action_post(self):
        res = super().action_post()
        self._chatroom_notify_invoice_posted()
        return res

    def _chatroom_notify_invoice_posted(self):
        """Aviso automático por WhatsApp cuando se publica (confirma)
        una factura de cliente, si hay una plantilla configurada en
        Ajustes > Chatroom WhatsApp. Mismo criterio que
        sale_order._chatroom_notify_order_confirmed(): plantilla
        aprobada (no texto libre) y solo a contactos que ya tienen una
        conversación de WhatsApp -no crea una nueva."""
        icp = self.env['ir.config_parameter'].sudo()
        template_id = icp.get_param('chatroom_whatsapp.notify_invoice_posted_template_id')
        if not template_id:
            return
        template = self.env['chatroom.template'].browse(int(template_id)).exists()
        if not template:
            return
        Channel = self.env['chatroom.channel']
        for move in self:
            if move.move_type != 'out_invoice' or not move.partner_id:
                continue
            channel = Channel.search([
                ('partner_id', '=', move.partner_id.id),
                ('channel_type', '=', 'whatsapp'),
            ], order='last_message_date desc', limit=1)
            if not channel:
                continue
            try:
                channel.action_send_template(
                    template.name, template.language, template.get_variable_values(channel))
            except UserError as exc:
                _logger.info(
                    "No se pudo mandar el aviso de factura publicada por WhatsApp "
                    "(factura %s): %s", move.name or move.id, exc)

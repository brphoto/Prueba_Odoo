# -*- coding: utf-8 -*-
import logging
from datetime import timedelta

from odoo import _, api, fields, models


_logger = logging.getLogger(__name__)


class ChatroomChannel(models.Model):
    _inherit = 'chatroom.channel'

    ai_sales_delivery_status = fields.Selection([
        ('idle', 'Sin despacho'),
        ('ready', 'Listo para despacho'),
        ('done', 'Entregado'),
        ('cancelled', 'Despacho cancelado'),
    ], string='Estado de entrega', default='idle', copy=False, index=True)
    ai_sales_last_picking_id = fields.Many2one(
        'stock.picking', string='Último despacho', copy=False, ondelete='set null')
    ai_sales_cart_reminder_count = fields.Integer(
        string='Recordatorios de carrito', default=0, copy=False)
    ai_sales_cart_last_reminder_at = fields.Datetime(
        string='Último recordatorio de carrito', copy=False)

    def _fulfillment_param_enabled(self, key, default=False):
        value = self.env['ir.config_parameter'].sudo().get_param(key)
        if value is None or value == '':
            return default
        return value == 'True'

    def _fulfillment_int_param(self, key, default):
        value = self.env['ir.config_parameter'].sudo().get_param(key, str(default))
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return default

    def _sales_validate_order(self, order):
        self.ensure_one()
        error = super()._sales_validate_order(order)
        if error:
            return error
        shipping = order.partner_shipping_id or order.partner_id
        if self._fulfillment_param_enabled('chatroom_ai_sales.require_delivery_address'):
            missing = []
            if not shipping.street:
                missing.append(_('calle y número'))
            if not shipping.city:
                missing.append(_('ciudad'))
            if not shipping.country_id:
                missing.append(_('país'))
            if missing:
                return _('Falta completar la dirección de entrega: %s. Un asesor debe validarla antes de confirmar.') % ', '.join(missing)
        if self._fulfillment_param_enabled('chatroom_ai_sales.require_stock'):
            for line in order.order_line:
                product = line.product_id
                if not product or product.type == 'service':
                    continue
                product_company = product.with_company(order.company_id)
                available = product_company.free_qty if 'free_qty' in product_company._fields else product_company.qty_available
                if available < line.product_uom_qty:
                    return _('No hay inventario suficiente para «%s» (disponible: %s; solicitado: %s).') % (
                        product.display_name, available, line.product_uom_qty)
        return False

    def _fulfillment_notify_delivery(self, picking, status):
        self.ensure_one()
        if status == 'ready':
            body = _('Tu pedido %s está preparado para despacho.') % picking.name
            event = 'delivery_ready'
            label = 'ready'
        elif status == 'done':
            body = _('Tu pedido %s fue entregado correctamente. Gracias por tu compra.') % picking.name
            event = 'delivery_done'
            label = 'done'
        else:
            body = _('El despacho %s fue cancelado. Un asesor revisará tu pedido.') % picking.name
            event = 'delivery_cancelled'
            label = 'cancelled'
        self.ai_sales_delivery_status = label
        self.ai_sales_last_picking_id = picking.id
        if self._fulfillment_param_enabled('chatroom_ai_sales.notify_delivery', True):
            self._sales_send_text(body)
        self._sales_log(event, body, order=picking.sale_id if 'sale_id' in picking._fields else False)

    @api.model
    def _fulfillment_cutoff(self, hours):
        return fields.Datetime.now() - timedelta(hours=hours)

    @api.model
    def _cron_ai_sales_fulfillment(self):
        """Run lightweight operational automations in one safe, retryable cron."""
        env = self.env
        channel_model = env['chatroom.channel'].sudo()
        if env['ir.config_parameter'].sudo().get_param('chatroom_ai_sales.cart_reminder_enabled') == 'True':
            hours = max(1, channel_model._fulfillment_int_param('chatroom_ai_sales.cart_reminder_hours', 24))
            max_reminders = max(1, channel_model._fulfillment_int_param('chatroom_ai_sales.cart_reminder_max', 1))
            cutoff = channel_model._fulfillment_cutoff(hours)
            channels = channel_model.search([
                ('channel_type', '=', 'whatsapp'),
                ('state', 'in', ('open', 'pending')),
                ('ai_paused', '=', False),
                ('cart_line_ids', '!=', False),
                ('ai_sales_cart_reminder_count', '<', max_reminders),
            ], limit=200)
            test_channel_id = env.context.get('chatroom_fulfillment_channel_id')
            if test_channel_id:
                channels = channels.filtered(lambda channel: channel.id == test_channel_id)
            for channel in channels:
                latest_cart_date = max(channel.cart_line_ids.mapped('create_date') or [False])
                if not latest_cart_date or latest_cart_date > cutoff:
                    continue
                if channel.ai_sales_cart_last_reminder_at and channel.ai_sales_cart_last_reminder_at > cutoff:
                    continue
                body = _('Veo que dejaste productos en tu carrito. Si deseas continuar, escríbeme y te ayudo a finalizar tu pedido.')
                channel._sales_send_text(body)
                channel.write({
                    'ai_sales_cart_reminder_count': channel.ai_sales_cart_reminder_count + 1,
                    'ai_sales_cart_last_reminder_at': fields.Datetime.now(),
                })
                channel._sales_log('cart_reminder', body, amount=channel.cart_total)
        return True

# -*- coding: utf-8 -*-
import re
import logging

from odoo import _, fields, models
from odoo.tools.float_utils import float_compare


_logger = logging.getLogger(__name__)


class ChatroomChannel(models.Model):
    _inherit = 'chatroom.channel'

    ai_sales_status = fields.Selection([
        ('idle', 'Sin venta en curso'),
        ('collecting', 'Armando carrito'),
        ('awaiting_confirmation', 'Esperando confirmación'),
        ('quotation', 'Cotización creada'),
        ('confirmed', 'Pedido confirmado'),
        ('payment_pending', 'Pago pendiente'),
        ('payment_received', 'Pago recibido'),
        ('post_sale', 'Postventa'),
        ('escalated', 'Revisión humana'),
    ], string='Estado de venta autónoma', default='idle', copy=False, index=True)
    ai_sales_last_order_id = fields.Many2one('sale.order', string='Último pedido autónomo', copy=False)
    ai_sales_last_error = fields.Text(string='Último bloqueo de venta', copy=False)
    ai_sales_reply_override = fields.Text(string='Respuesta comercial pendiente', copy=False)

    def _sales_param_enabled(self, key):
        return self.env['ir.config_parameter'].sudo().get_param(key, 'False') == 'True'

    def _sales_log(self, event, details=False, order=False, amount=0.0):
        self.ensure_one()
        if 'chatroom.ai.sales.event' not in self.env:
            return
        self.env['chatroom.ai.sales.event'].sudo().create({
            'name': _('Venta autónoma - %s') % self.display_name,
            'channel_id': self.id,
            'order_id': order.id if order else False,
            'event': event,
            'amount': amount or (order.amount_total if order else 0.0),
            'currency_id': (order.currency_id.id if order and order.currency_id else self.env.company.currency_id.id),
            'details': details or False,
        })

    def _sales_latest_inbound(self):
        self.ensure_one()
        message_id = self.env.context.get('chatroom_ai_autonomous_message_id')
        if message_id:
            message = self.env['chatroom.message'].browse(message_id).exists()
            if message and message.direction == 'inbound':
                return message
        return self.message_ids.filtered(lambda message: message.direction == 'inbound').sorted('date')[-1:]

    def _sales_has_explicit_confirmation(self):
        message = self._sales_latest_inbound()
        body = (message.body or '').strip().lower() if message else ''
        return bool(re.search(
            r'\b(confirmo|confirmar|acepto|aceptado|adelante|hazlo|proceder|'
            r'comprar ahora|quiero comprar|realiza(r)? el pedido|hacer el pedido|'
            r'sí,? quiero|si,? quiero|pagar ahora|envíame el link|enviame el link)\b',
            body,
        ))

    def _ai_autonomous_checkout_guard(self):
        """Guard called by the existing WhatsApp cart assistant before checkout."""
        self.ensure_one()
        if not self.env.context.get('chatroom_ai_autonomous_checkout'):
            return False
        if not self._sales_param_enabled('chatroom_ai_sales.enabled'):
            return False
        if self._sales_param_enabled('chatroom_ai_sales.auto_confirm') and not self._sales_has_explicit_confirmation():
            reason = _('Para cerrar el pedido necesito que confirmes explícitamente: «Sí, quiero comprar».')
            self.ai_sales_status = 'awaiting_confirmation'
            self._sales_log('confirmation_requested', reason)
            return reason
        cart_error = self._sales_validate_cart()
        if cart_error:
            self.ai_sales_status = 'escalated'
            self.ai_sales_last_error = cart_error
            self.ai_sales_reply_override = cart_error + ' ' + _('Un asesor continuará contigo.')
            self._sales_log('blocked', cart_error, amount=self.cart_total)
            return cart_error
        # La política de autonomía, si está instalada, es el último control
        # antes de crear o confirmar una venta. La dependencia sigue siendo
        # opcional para conservar la modularidad.
        if 'chatroom.ai.autonomy.policy' in self.env:
            policy = self.env['chatroom.ai.autonomy.policy'].get_active_policy(self.company_id)
            if policy:
                decision = policy.evaluate(
                    'confirm_order', self.cart_total, 1.0, channel=self)
                if decision['decision'] != 'allow':
                    reason = decision['reason']
                    self.ai_sales_status = (
                        'awaiting_confirmation'
                        if decision['decision'] == 'approval' else 'escalated')
                    self.ai_sales_last_error = reason
                    self.ai_sales_reply_override = reason
                    self._sales_log(
                        'confirmation_requested'
                        if decision['decision'] == 'approval' else 'blocked',
                        reason, amount=self.cart_total)
                    return reason
        return False

    def _sales_send_text(self, body):
        self.ensure_one()
        try:
            return self.with_context(chatroom_ai_generated=True).action_send_text(body)
        except Exception as exc:  # noqa: BLE001 - no romper el webhook
            _logger.warning('No se pudo enviar mensaje comercial del canal %s: %s', self.id, exc)
            return False

    def _sales_validate_order(self, order):
        self.ensure_one()
        limit_raw = self.env['ir.config_parameter'].sudo().get_param(
            'chatroom_ai_sales.max_auto_amount', '0') or '0'
        try:
            limit = float(limit_raw)
        except (TypeError, ValueError):
            limit = 0.0
        if limit <= 0:
            return _('La confirmación automática está activa, pero falta configurar un monto máximo mayor que cero.')
        if order.amount_total > limit:
            return _('El pedido supera el límite automático de %s %s.') % (
                order.currency_id.symbol or order.currency_id.name, limit)
        invalid = order.order_line.filtered(
            lambda line: not line.product_id.active or not line.product_id.sale_ok or line.discount)
        if invalid:
            return _('El pedido contiene productos inactivos, no vendibles o con descuento; requiere revisión humana.')
        return False

    def _sales_validate_cart(self):
        self.ensure_one()
        icp = self.env['ir.config_parameter'].sudo()
        validate_stock = icp.get_param('chatroom_ai_sales.validate_stock', 'True') == 'True'
        validate_price = icp.get_param('chatroom_ai_sales.validate_price', 'True') == 'True'
        currency = self.env.company.currency_id
        for cart_line in self.cart_line_ids:
            product = self.env['product.product'].browse(cart_line.product_id).exists()
            if not product or not product.active or not product.sale_ok:
                return _('El producto %s ya no está disponible para la venta.') % (cart_line.product_name or cart_line.product_id)
            current_price = product.lst_price
            if hasattr(self, '_ai_product_commercial_data'):
                current_price = self._ai_product_commercial_data(
                    product, quantity=cart_line.quantity)['price']
            if validate_price and float_compare(
                    cart_line.price_unit, current_price,
                    precision_rounding=currency.rounding):
                return _('El precio de %s cambió desde que se agregó al carrito; requiere revisión.') % product.display_name
            if validate_stock and product.type == 'consu' and product.is_storable:
                available = product.with_company(self.company_id).free_qty
                if available < cart_line.quantity:
                    return _('La existencia de %s es insuficiente: disponible %s, solicitado %s.') % (
                        product.display_name, available, cart_line.quantity)
        return False

    def _sales_after_checkout(self, order):
        self.ensure_one()
        self.ai_sales_last_order_id = order.id
        self.ai_sales_last_error = False
        if not self._sales_param_enabled('chatroom_ai_sales.auto_confirm'):
            self.ai_sales_status = 'quotation'
            self._sales_log('quotation_created', _('Cotización creada; confirmación humana configurada.'), order=order)
            return
        error = self._sales_validate_order(order)
        if error:
            self.ai_sales_status = 'escalated'
            self.ai_sales_last_error = error
            self.ai_sales_reply_override = error + ' ' + _('Un asesor continuará contigo.')
            self._sales_log('blocked', error, order=order)
            return
        try:
            order.action_confirm()
        except Exception as exc:  # noqa: BLE001 - conservar cotización para revisión
            error = _('No se pudo confirmar automáticamente el pedido: %s') % exc
            self.ai_sales_status = 'escalated'
            self.ai_sales_last_error = error
            self.ai_sales_reply_override = _('Tu pedido quedó preparado, pero un asesor debe finalizarlo.')
            self._sales_log('escalated', error, order=order)
            return
        self.ai_sales_status = 'confirmed'
        self._sales_log('order_confirmed', _('Pedido confirmado tras confirmación explícita del cliente.'), order=order)
        if self._sales_param_enabled('chatroom_ai_sales.auto_payment_link'):
            if not hasattr(self, 'action_send_payment_link'):
                error = _('No existe un conector de enlaces de pago instalado.')
            else:
                try:
                    self.action_send_payment_link('sale.order', order.id)
                    self.ai_sales_status = 'payment_pending'
                    self._sales_log('payment_link_sent', _('Se utilizó el conector de pagos configurado.'), order=order)
                    self.ai_sales_reply_override = '__SUPPRESS__'
                    return
                except Exception as exc:  # noqa: BLE001 - escalar sin romper el mensaje
                    error = _('El pedido fue confirmado, pero no se pudo enviar el link de pago: %s') % exc
            self.ai_sales_status = 'escalated'
            self.ai_sales_last_error = error
            self.ai_sales_reply_override = _('Tu pedido fue confirmado. Un asesor te enviará el enlace de pago.')
            self._sales_log('escalated', error, order=order)
            return
        self.ai_sales_reply_override = _('Tu pedido fue confirmado correctamente. Gracias por tu compra.')

    def action_checkout_cart(self):
        self.ensure_one()
        guard = self._ai_autonomous_checkout_guard()
        if guard:
            self.ai_sales_reply_override = guard
            return False
        order_id = super().action_checkout_cart()
        order = self.env['sale.order'].browse(order_id).exists() if order_id else self.env['sale.order'].browse()
        if order:
            self._sales_after_checkout(order)
        return order_id

    def _ai_process_inbound_message(self, message):
        self.ensure_one()
        if (
            self._sales_param_enabled('chatroom_ai_sales.enabled')
            and self.channel_type == 'whatsapp'
            and not self.ai_paused
        ):
            # El módulo de WhatsApp conserva el catálogo/carrito y el modelo
            # configurado; solo añade el checkout protegido de esta capa.
            self = self.with_context(
                chatroom_ai_autonomous_checkout=True,
                chatroom_ai_autonomous_message_id=message.id,
            )
            self.ai_sales_status = 'collecting' if self.cart_line_ids else 'idle'
        return super()._ai_process_inbound_message(message)

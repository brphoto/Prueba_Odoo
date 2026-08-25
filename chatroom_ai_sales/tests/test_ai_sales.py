# -*- coding: utf-8 -*-
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestChatroomAiSales(TransactionCase):

    def setUp(self):
        super().setUp()
        self.icp = self.env['ir.config_parameter'].sudo()
        self.icp.set_param('chatroom_ai_sales.enabled', 'True')
        self.icp.set_param('chatroom_ai_sales.auto_confirm', 'True')
        self.icp.set_param('chatroom_ai_sales.auto_payment_link', 'False')
        self.icp.set_param('chatroom_ai_sales.validate_stock', 'False')
        self.icp.set_param('chatroom_ai_sales.validate_price', 'True')
        self.partner = self.env['res.partner'].create({'name': 'Cliente venta autónoma', 'phone': '+593999111222'})
        self.channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp',
            'external_id': 'ai-sales-test-%s' % self.partner.id,
            'partner_id': self.partner.id,
        })
        template = self.env['product.template'].create({
            'name': 'Producto venta autónoma',
            'list_price': 25.0,
            'sale_ok': True,
        })
        self.product = template.product_variant_id

    def _cart(self, quantity=1.0):
        return self.env['chatroom.cart.line'].create({
            'channel_id': self.channel.id,
            'product_id': self.product.id,
            'product_name': self.product.display_name,
            'quantity': quantity,
            'price_unit': self.product.lst_price,
        })

    def test_explicit_confirmation_confirms_below_limit(self):
        self.icp.set_param('chatroom_ai_sales.max_auto_amount', '100')
        message = self.env['chatroom.message'].create({
            'channel_id': self.channel.id,
            'direction': 'inbound',
            'message_type': 'text',
            'body': 'Sí, quiero comprar',
        })
        self._cart()
        order_id = self.channel.with_context(
            chatroom_ai_autonomous_checkout=True,
            chatroom_ai_autonomous_message_id=message.id,
        ).action_checkout_cart()
        order = self.env['sale.order'].browse(order_id)
        self.assertEqual(order.state, 'sale')
        self.assertEqual(self.channel.ai_sales_status, 'confirmed')
        self.assertTrue(self.env['chatroom.ai.sales.event'].search_count([
            ('channel_id', '=', self.channel.id), ('event', '=', 'order_confirmed'),
        ]))

    def test_auto_confirmation_requires_explicit_customer_confirmation(self):
        self.icp.set_param('chatroom_ai_sales.max_auto_amount', '100')
        message = self.env['chatroom.message'].create({
            'channel_id': self.channel.id,
            'direction': 'inbound',
            'message_type': 'text',
            'body': '¿Cuánto cuesta?',
        })
        self._cart()
        result = self.channel.with_context(
            chatroom_ai_autonomous_checkout=True,
            chatroom_ai_autonomous_message_id=message.id,
        ).action_checkout_cart()
        self.assertFalse(result)
        self.assertEqual(self.channel.ai_sales_status, 'awaiting_confirmation')
        self.assertFalse(self.env['sale.order'].search([('partner_id', '=', self.partner.id)]))

    def test_limit_blocks_automatic_confirmation_and_keeps_draft(self):
        self.icp.set_param('chatroom_ai_sales.max_auto_amount', '10')
        message = self.env['chatroom.message'].create({
            'channel_id': self.channel.id,
            'direction': 'inbound',
            'message_type': 'text',
            'body': 'Confirmo el pedido',
        })
        self._cart()
        order_id = self.channel.with_context(
            chatroom_ai_autonomous_checkout=True,
            chatroom_ai_autonomous_message_id=message.id,
        ).action_checkout_cart()
        order = self.env['sale.order'].browse(order_id)
        self.assertEqual(order.state, 'draft')
        self.assertEqual(self.channel.ai_sales_status, 'escalated')
        self.assertTrue(self.channel.ai_sales_last_error)

    def test_price_drift_requires_human_review_before_checkout(self):
        self.icp.set_param('chatroom_ai_sales.max_auto_amount', '100')
        self.icp.set_param('chatroom_ai_sales.auto_confirm', 'False')
        message = self.env['chatroom.message'].create({
            'channel_id': self.channel.id,
            'direction': 'inbound',
            'message_type': 'text',
            'body': 'Confirmo el pedido',
        })
        self._cart()
        self.channel.cart_line_ids.price_unit = self.product.lst_price + 1
        result = self.channel.with_context(
            chatroom_ai_autonomous_checkout=True,
            chatroom_ai_autonomous_message_id=message.id,
        ).action_checkout_cart()
        self.assertFalse(result)
        self.assertEqual(self.channel.ai_sales_status, 'escalated')
        self.assertIn('precio', self.channel.ai_sales_last_error.lower())

    def test_stock_validation_blocks_empty_inventory(self):
        self.icp.set_param('chatroom_ai_sales.max_auto_amount', '100')
        self.icp.set_param('chatroom_ai_sales.auto_confirm', 'False')
        self.icp.set_param('chatroom_ai_sales.validate_stock', 'True')
        self.product.is_storable = True
        message = self.env['chatroom.message'].create({
            'channel_id': self.channel.id,
            'direction': 'inbound',
            'message_type': 'text',
            'body': 'Confirmo el pedido',
        })
        self._cart()
        result = self.channel.with_context(
            chatroom_ai_autonomous_checkout=True,
            chatroom_ai_autonomous_message_id=message.id,
        ).action_checkout_cart()
        self.assertFalse(result)
        self.assertEqual(self.channel.ai_sales_status, 'escalated')
        self.assertIn('existencia', self.channel.ai_sales_last_error.lower())

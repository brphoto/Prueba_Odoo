# -*- coding: utf-8 -*-
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestChatroomAiSalesFulfillment(TransactionCase):

    def setUp(self):
        super().setUp()
        self.icp = self.env['ir.config_parameter'].sudo()
        self.icp.set_param('chatroom_ai_sales.enabled', 'True')
        self.icp.set_param('chatroom_ai_sales.auto_confirm', 'True')
        self.icp.set_param('chatroom_ai_sales.auto_payment_link', 'False')
        self.icp.set_param('chatroom_ai_sales.max_auto_amount', '1000')
        self.icp.set_param('chatroom_ai_sales.require_stock', 'False')
        self.icp.set_param('chatroom_ai_sales.require_delivery_address', 'False')
        self.partner = self.env['res.partner'].create({
            'name': 'QA Fulfillment Cliente',
            'phone': '+593999555111',
        })
        self.channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp',
            'external_id': 'fulfillment-test-%s' % self.partner.id,
            'partner_id': self.partner.id,
        })
        template = self.env['product.template'].create({
            'name': 'QA Fulfillment Producto',
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

    def _confirm_order(self):
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
        return self.env['sale.order'].browse(order_id)

    def test_full_flow_cart_to_confirmed_order(self):
        order = self._confirm_order()
        self.assertEqual(order.state, 'sale')
        self.assertEqual(self.channel.ai_sales_status, 'confirmed')
        self.assertTrue(self.env['chatroom.ai.sales.event'].search_count([
            ('channel_id', '=', self.channel.id),
            ('event', '=', 'order_confirmed'),
        ]))

    def test_delivery_status_is_visible_and_audited(self):
        order = self._confirm_order()
        picking_type = self.env['stock.picking.type'].search([
            ('code', '=', 'outgoing'),
            ('company_id', '=', self.env.company.id),
        ], limit=1)
        if not picking_type:
            self.skipTest('No existe un tipo de operación de salida en esta base.')
        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type.id,
            'partner_id': self.partner.id,
            'origin': order.name,
            'location_id': picking_type.default_location_src_id.id,
            'location_dest_id': picking_type.default_location_dest_id.id,
        })
        self.channel.ai_sales_last_order_id = order.id
        with patch.object(type(self.channel), '_sales_send_text', return_value=True):
            self.channel._fulfillment_notify_delivery(picking, 'ready')
        self.assertEqual(self.channel.ai_sales_delivery_status, 'ready')
        self.assertEqual(self.channel.ai_sales_last_picking_id, picking)
        self.assertTrue(self.env['chatroom.ai.sales.event'].search_count([
            ('channel_id', '=', self.channel.id),
            ('event', '=', 'delivery_ready'),
        ]))

    def test_address_policy_blocks_incomplete_delivery_address(self):
        self.icp.set_param('chatroom_ai_sales.require_delivery_address', 'True')
        order = self.env['sale.order'].create({'partner_id': self.partner.id})
        error = self.channel._sales_validate_order(order)
        self.assertIn('dirección', error)

    def test_stock_policy_blocks_unavailable_product(self):
        self.icp.set_param('chatroom_ai_sales.require_stock', 'True')
        order = self.env['sale.order'].create({'partner_id': self.partner.id})
        self.env['sale.order.line'].create({
            'order_id': order.id,
            'product_id': self.product.id,
            'product_uom_qty': 1,
            'price_unit': self.product.lst_price,
        })
        self.assertIn('inventario', self.channel._sales_validate_order(order).lower())

    def test_abandoned_cart_cron_reminds_once(self):
        self.icp.set_param('chatroom_ai_sales.cart_reminder_enabled', 'True')
        self.icp.set_param('chatroom_ai_sales.cart_reminder_hours', '1')
        self.icp.set_param('chatroom_ai_sales.cart_reminder_max', '1')
        self._cart()
        # La base de pruebas contiene demos previos; este caso debe validar
        # únicamente el carrito recién creado y no intentar tocar WhatsApp
        # de esos registros históricos.
        self.env['chatroom.channel'].search([
            ('id', '!=', self.channel.id),
            ('cart_line_ids', '!=', False),
        ]).write({'state': 'closed'})
        old_date = fields.Datetime.now() - timedelta(hours=2)
        self.env.cr.execute(
            'UPDATE chatroom_cart_line SET create_date = %s WHERE channel_id = %s',
            (old_date, self.channel.id),
        )
        self.env['chatroom.cart.line'].invalidate_model(['create_date'])
        with patch.object(type(self.channel), '_sales_send_text', return_value=True):
            self.env['chatroom.channel'].with_context(
                chatroom_fulfillment_channel_id=self.channel.id,
            )._cron_ai_sales_fulfillment()
        self.channel.invalidate_recordset()
        self.assertEqual(self.channel.ai_sales_cart_reminder_count, 1)
        self.assertTrue(self.env['chatroom.ai.sales.event'].search_count([
            ('channel_id', '=', self.channel.id),
            ('event', '=', 'cart_reminder'),
        ]))

    def test_failed_payment_retry_is_limited_and_audited(self):
        self.icp.set_param('chatroom_ai_sales.payment_retry_enabled', 'True')
        self.icp.set_param('chatroom_ai_sales.payment_retry_hours', '1')
        self.icp.set_param('chatroom_ai_sales.payment_retry_max', '1')
        self.icp.set_param('chatroom_ai_sales.notify_payment', 'False')
        self.icp.set_param('chatroom_ai_sales.auto_create_invoice', 'False')
        self.env['chatroom.payment.link'].search([('state', '=', 'paid')]).write({
            'ai_sales_postprocessed': True,
            'ai_sales_payment_notified': True,
        })
        link = self.env['chatroom.payment.link'].create({
            'name': 'QA enlace fallido',
            'channel_id': self.channel.id,
            'res_model': 'sale.order',
            'res_id': 0,
            'document_name': 'QA pedido',
            'link': 'https://example.test/qa-payment',
            'state': 'error',
            'amount': 25.0,
            'currency_id': self.env.company.currency_id.id,
        })
        old_date = fields.Datetime.now() - timedelta(hours=2)
        self.env.cr.execute('UPDATE chatroom_payment_link SET create_date = %s WHERE id = %s', (old_date, link.id))

        def resend():
            link.write({'state': 'sent'})
            return True

        with patch.object(type(link), 'action_resend', side_effect=resend):
            link._cron_sync_transaction_states()
        link.invalidate_recordset()
        self.assertEqual(link.ai_sales_retry_attempts, 1)
        self.assertEqual(link.state, 'sent')

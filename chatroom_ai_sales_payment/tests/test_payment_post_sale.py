# -*- coding: utf-8 -*-
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestChatroomAiSalesPayment(TransactionCase):

    def setUp(self):
        super().setUp()
        self.icp = self.env['ir.config_parameter'].sudo()
        self.icp.set_param('chatroom_ai_sales.enabled', 'True')
        self.icp.set_param('chatroom_ai_sales.notify_payment', 'True')
        self.icp.set_param('chatroom_ai_sales.auto_create_invoice', 'False')
        partner = self.env['res.partner'].create({'name': 'Cliente postventa', 'phone': '+593999333444'})
        self.channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp',
            'external_id': 'post-sale-test-%s' % partner.id,
            'partner_id': partner.id,
        })
        self.order = self.env['sale.order'].create({'partner_id': partner.id})

    def _link(self):
        return self.env['chatroom.payment.link'].create({
            'name': 'Pago postventa de prueba',
            'channel_id': self.channel.id,
            'res_model': 'sale.order',
            'res_id': self.order.id,
            'document_name': self.order.name,
            'link': 'https://example.test/payment/1',
            'state': 'paid',
            'amount': 10.0,
            'currency_id': self.env.company.currency_id.id,
        })

    def test_paid_link_is_processed_once_and_notified(self):
        link = self._link()
        with patch.object(type(self.channel), '_sales_send_text', return_value=True):
            link._cron_sync_transaction_states()
        self.assertTrue(link.ai_sales_postprocessed)
        self.assertTrue(link.ai_sales_payment_notified)
        self.assertEqual(self.channel.ai_sales_status, 'post_sale')
        self.assertEqual(
            self.env['chatroom.ai.sales.event'].search_count([
                ('channel_id', '=', self.channel.id),
                ('event', 'in', ('payment_received', 'post_sale_notified')),
            ]),
            2,
        )

    def test_post_sale_failure_is_kept_for_retry(self):
        link = self._link()
        with patch.object(type(self.channel), '_sales_send_text', return_value=False):
            link._cron_sync_transaction_states()
        self.assertFalse(link.ai_sales_postprocessed)
        self.assertEqual(link.ai_sales_postprocess_attempts, 1)
        self.assertTrue(link.ai_sales_postprocess_error)

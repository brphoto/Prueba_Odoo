# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo.fields import Datetime
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestChatroomSalesIntelligence(TransactionCase):

    def test_chatroom_channel_resolves_pinned_lead_for_alert(self):
        partner = self.env['res.partner'].create({'name': "Cliente Chatroom"})
        lead = self.env['crm.lead'].create({'name': "Oportunidad anclada", 'partner_id': partner.id})
        lead.write({'date_last_stage_update': Datetime.now() - timedelta(days=10)})
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp',
            'external_id': '573000000001',
            'partner_id': partner.id,
            'pinned_lead_id': lead.id,
        })

        self.assertEqual(channel.management_alert_state, 'yellow')
        self.assertGreaterEqual(channel.management_days_stagnant, 7)

    def test_get_commercial_intelligence_without_partner(self):
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp',
            'external_id': '573000000002',
        })
        data = channel.get_commercial_intelligence()
        self.assertFalse(data['has_partner'])

    def test_get_commercial_intelligence_structure(self):
        partner = self.env['res.partner'].create({'name': "Cliente con Intel"})
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp',
            'external_id': '573000000003',
            'partner_id': partner.id,
        })
        data = channel.get_commercial_intelligence()
        self.assertTrue(data['has_partner'])
        for key in ('rfm_category', 'rfm_score', 'commercial_total_sales',
                    'commercial_invoice_count', 'top_products'):
            self.assertIn(key, data)

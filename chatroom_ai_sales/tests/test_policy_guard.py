# -*- coding: utf-8 -*-
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestChatroomAiSalesPolicyGuard(TransactionCase):

    def test_active_autonomy_policy_can_be_selected_for_sales(self):
        if 'chatroom.ai.autonomy.policy' not in self.env:
            self.skipTest('El mÃ³dulo de autonomÃ­a es opcional.')
        policy_model = self.env['chatroom.ai.autonomy.policy']
        policy_model.search([]).write({'active': False})
        policy_model.create({
            'name': 'Control comercial',
            'mode': 'approval',
            'allow_order': True,
        })
        partner = self.env['res.partner'].create({'name': 'Cliente de control comercial'})
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp',
            'external_id': 'policy-guard-%s' % partner.id,
            'partner_id': partner.id,
        })
        self.env['ir.config_parameter'].sudo().set_param('chatroom_ai_sales.enabled', 'True')
        result = channel.with_context(chatroom_ai_autonomous_checkout=True)._ai_autonomous_checkout_guard()
        self.assertTrue(result)
        self.assertEqual(channel.ai_sales_status, 'awaiting_confirmation')

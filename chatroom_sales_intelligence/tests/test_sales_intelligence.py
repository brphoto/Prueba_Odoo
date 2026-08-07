# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo.exceptions import UserError
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

    def test_my_pending_followups_only_lists_stagnant_own_records(self):
        partner = self.env['res.partner'].create({'name': "Cliente Pendiente"})
        stale_channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp',
            'external_id': '573000000004',
            'partner_id': partner.id,
            'assigned_user_id': self.env.uid,
            'state': 'open',
        })
        stale_channel.pinned_lead_id = self.env['crm.lead'].create({
            'name': "Oportunidad estancada del panel", 'partner_id': partner.id,
        }).id
        self.env['crm.lead'].browse(stale_channel.pinned_lead_id).write(
            {'date_last_stage_update': Datetime.now() - timedelta(days=20)})

        fresh_channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp',
            'external_id': '573000000005',
            'assigned_user_id': self.env.uid,
            'state': 'open',
        })

        other_user_lead = self.env['crm.lead'].create({
            'name': "Oportunidad de otro vendedor", 'user_id': False})
        other_user_lead.write({'date_last_stage_update': Datetime.now() - timedelta(days=20)})

        data = self.env['chatroom.channel'].get_my_pending_followups()

        channel_ids = [row['id'] for row in data['channels']]
        self.assertIn(stale_channel.id, channel_ids)
        self.assertNotIn(fresh_channel.id, channel_ids)
        self.assertNotIn(other_user_lead.id, [row['id'] for row in data['leads']])

    def test_campaign_recipient_count_respects_rfm_and_opt_out(self):
        partner_a = self.env['res.partner'].create({'name': "Cliente A", 'phone': "+573002000001"})
        partner_a.rfm_category = 'a'
        partner_b_opted_out = self.env['res.partner'].create({
            'name': "Cliente B dado de baja", 'phone': "+573002000002", 'whatsapp_opt_out': True})
        partner_b_opted_out.rfm_category = 'b'
        partner_c_no_phone = self.env['res.partner'].create({'name': "Cliente C sin teléfono"})
        partner_c_no_phone.rfm_category = 'c'

        campaign = self.env['chatroom.campaign'].create({
            'name': "Campaña test",
            'template_id': self.env['chatroom.template'].create({
                'name': 'test_campaign_template', 'language': 'es',
                'body': "Hola {{1}}, tenemos una promo para vos.", 'status': 'approved',
            }).id,
            'target_rfm_a': True, 'target_rfm_b': True, 'target_rfm_c': True,
        })

        partners = campaign._get_target_partners()
        self.assertIn(partner_a, partners)
        self.assertNotIn(partner_b_opted_out, partners, "no debe incluir contactos dados de baja")
        self.assertNotIn(partner_c_no_phone, partners, "no debe incluir contactos sin teléfono")
        self.assertEqual(campaign.recipient_count, len(partners))

    def test_campaign_send_without_target_categories_raises(self):
        campaign = self.env['chatroom.campaign'].create({
            'name': "Campaña vacía",
            'template_id': self.env['chatroom.template'].create({
                'name': 'test_campaign_template_2', 'language': 'es', 'body': "Hola.",
                'status': 'approved',
            }).id,
            'target_rfm_a': False, 'target_rfm_b': False, 'target_rfm_c': False,
        })

        with self.assertRaises(UserError):
            campaign.action_send()

    def test_campaign_send_only_queues_recipients(self):
        """action_send ya no manda nada: solo toma la foto de
        destinatarios y pasa a 'sending'. El envío real lo hace el cron
        (ver test_campaign_cron_processes_batch_and_finishes)."""
        partner = self.env['res.partner'].create({'name': "Cliente Cola", 'phone': "+573002000004"})
        partner.rfm_category = 'a'
        campaign = self.env['chatroom.campaign'].create({
            'name': "Campaña en cola",
            'template_id': self.env['chatroom.template'].create({
                'name': 'test_campaign_template_4', 'language': 'es', 'body': "Hola.",
                'status': 'approved',
            }).id,
            'target_rfm_a': True, 'target_rfm_b': False, 'target_rfm_c': False,
        })

        campaign.action_send()

        self.assertEqual(campaign.state, 'sending')
        self.assertEqual(campaign.pending_count, 1)
        self.assertEqual(len(campaign.recipient_ids), 1)
        self.assertEqual(campaign.recipient_ids.partner_id, partner)
        self.assertTrue(campaign.queued_date)
        self.assertFalse(campaign.sent_date, "todavía no terminó de mandarse")

    def test_campaign_cron_processes_batch_and_finishes(self):
        """Sin credenciales de WhatsApp configuradas, cada envío individual
        falla, pero el lote no debe romperse: la primera corrida del cron
        marca los destinatarios como fallidos, y una segunda corrida (sin
        pendientes) cierra la campaña en 'sent' con el detalle."""
        self.env['ir.config_parameter'].sudo().set_param('chatroom_whatsapp.access_token', False)
        self.env['ir.config_parameter'].sudo().set_param('chatroom_whatsapp.phone_number_id', False)
        partner = self.env['res.partner'].create({'name': "Cliente Campaña", 'phone': "+573002000003"})
        partner.rfm_category = 'a'
        campaign = self.env['chatroom.campaign'].create({
            'name': "Campaña sin credenciales",
            'template_id': self.env['chatroom.template'].create({
                'name': 'test_campaign_template_3', 'language': 'es', 'body': "Hola.",
                'status': 'approved',
            }).id,
            'target_rfm_a': True, 'target_rfm_b': False, 'target_rfm_c': False,
        })
        campaign.action_send()

        self.env['chatroom.campaign']._cron_process_campaigns()
        self.assertEqual(campaign.state, 'sending', "todavía debe cerrar en la próxima corrida")
        self.assertEqual(campaign.failed_count, 1)
        self.assertEqual(campaign.pending_count, 0)

        self.env['chatroom.campaign']._cron_process_campaigns()
        self.assertEqual(campaign.state, 'sent')
        self.assertEqual(campaign.sent_count, 0)
        self.assertEqual(campaign.failed_count, 1)
        self.assertTrue(campaign.sent_date)

    def test_campaign_cron_respects_batch_size(self):
        """Con batch_size=2 y 3 destinatarios, la primera corrida procesa
        solo 2 (deja 1 pendiente y sigue en 'sending')."""
        self.env['ir.config_parameter'].sudo().set_param('chatroom_whatsapp.access_token', False)
        self.env['ir.config_parameter'].sudo().set_param('chatroom_whatsapp.phone_number_id', False)
        for i in range(3):
            partner = self.env['res.partner'].create({
                'name': f"Cliente Lote {i}", 'phone': f"+57300210000{i}"})
            partner.rfm_category = 'a'
        campaign = self.env['chatroom.campaign'].create({
            'name': "Campaña con lotes",
            'template_id': self.env['chatroom.template'].create({
                'name': 'test_campaign_template_5', 'language': 'es', 'body': "Hola.",
                'status': 'approved',
            }).id,
            'target_rfm_a': True, 'batch_size': 2,
        })
        campaign.action_send()
        self.assertEqual(campaign.pending_count, 3)

        self.env['chatroom.campaign']._cron_process_campaigns()
        self.assertEqual(campaign.state, 'sending')
        self.assertEqual(campaign.failed_count, 2)
        self.assertEqual(campaign.pending_count, 1)

        self.env['chatroom.campaign']._cron_process_campaigns()
        self.assertEqual(campaign.state, 'sending')
        self.assertEqual(campaign.failed_count, 3)
        self.assertEqual(campaign.pending_count, 0)

        self.env['chatroom.campaign']._cron_process_campaigns()
        self.assertEqual(campaign.state, 'sent')

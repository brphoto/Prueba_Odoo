# -*- coding: utf-8 -*-
import base64
from io import BytesIO
from datetime import timedelta

from odoo.exceptions import UserError, ValidationError
from odoo.fields import Datetime
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestChatroomSalesIntelligence(TransactionCase):

    def test_knowledge_requires_content_before_indexing(self):
        with self.assertRaises(ValidationError):
            self.env['ai.knowledge.base'].create({
                'name': 'Conocimiento vacío test',
                'source_type': 'text',
            })

    def test_knowledge_text_is_indexed_and_company_scoped(self):
        manual = self.env['ai.knowledge.base'].create({
            'name': 'Política de garantía test',
            'source_type': 'text',
            'source_text': 'La garantía comercial cubre defectos de fabricación por 12 meses.',
            'keyword_tags': 'garantía, devolución',
        })
        manual.action_index()
        self.assertEqual(manual.state, 'indexed')
        self.assertIn('12 meses', manual.content_text)

        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp', 'external_id': '573000000099',
        })
        context = manual.get_sales_context(channel, query='garantía')
        self.assertIn('La garantía comercial', context)
        self.assertIn(self.env.company.name, context)

    def test_knowledge_pdf_uses_available_reader_and_preserves_text(self):
        """A PDF must work with the PyPDF2 fallback used by this server."""
        try:
            from reportlab.pdfgen import canvas
        except ImportError:
            self.skipTest('reportlab no está instalado en el entorno de pruebas')
        stream = BytesIO()
        pdf = canvas.Canvas(stream)
        pdf.drawString(72, 720, 'Odoo CRM - tarifa de implementacion USD 20 por hora')
        pdf.drawString(72, 700, 'Soporte, desarrollo personalizado y WhatsApp')
        pdf.save()
        manual = self.env['ai.knowledge.base'].create({
            'name': 'Manual PDF funcional test', 'source_type': 'pdf',
            'pdf_filename': 'manual_prueba.pdf',
            'pdf_file': base64.b64encode(stream.getvalue()),
        })
        manual.action_index()
        self.assertEqual(manual.state, 'indexed')
        self.assertGreaterEqual(manual.chunk_count, 1)
        self.assertIn('USD 20', manual.content_text)
        self.assertFalse(manual.processing_error)

    def test_knowledge_pdf_without_selectable_text_explains_next_step(self):
        try:
            from reportlab.pdfgen import canvas
        except ImportError:
            self.skipTest('reportlab no está instalado en el entorno de pruebas')
        stream = BytesIO()
        pdf = canvas.Canvas(stream)
        pdf.rect(72, 650, 220, 80, stroke=1, fill=0)
        pdf.save()
        manual = self.env['ai.knowledge.base'].create({
            'name': 'PDF escaneado test', 'source_type': 'pdf',
            'pdf_filename': 'escaneado.pdf',
            'pdf_file': base64.b64encode(stream.getvalue()),
        })
        manual.action_index()
        self.assertEqual(manual.state, 'error')
        self.assertIn('texto seleccionable', manual.processing_error)

    def test_knowledge_has_review_lifecycle(self):
        manual = self.env['ai.knowledge.base'].create({
            'name': 'Manual con revisión', 'source_type': 'text',
            'source_text': 'Contenido vigente para revisión.',
            'review_interval_days': 30,
        })
        self.assertEqual(manual.review_state, 'pending')
        manual.action_index()
        self.assertEqual(manual.review_state, 'current')
        self.assertTrue(manual.last_reviewed_at)
        self.assertTrue(manual.review_due_date)

    def test_knowledge_index_is_idempotent_and_context_is_bounded(self):
        manual = self.env['ai.knowledge.base'].create({
            'name': 'Manual de eficiencia IA test',
            'source_type': 'text',
            'source_text': 'Entrega estándar en 24 horas. ' + ('Detalle operativo. ' * 900),
        })
        manual.action_index()
        first_digest = manual.source_digest
        first_indexed_at = manual.indexed_at
        manual.action_index()
        self.assertEqual(manual.source_digest, first_digest)
        self.assertEqual(manual.indexed_at, first_indexed_at)
        manual.write({'source_text': 'Contenido actualizado de garantía.'})
        self.assertEqual(manual.state, 'pending')
        self.assertFalse(manual.content_text)
        manual.action_index()
        self.assertNotEqual(manual.source_digest, first_digest)
        self.env['ir.config_parameter'].sudo().set_param(
            'chatroom_ai.knowledge_context_max_chars', '3000')
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp', 'external_id': '573000000101',
        })
        context = manual.get_sales_context(channel, query='entrega')
        self.assertLessEqual(len(context), 3000)

    def test_knowledge_source_changes_create_a_new_version(self):
        manual = self.env['ai.knowledge.base'].create({
            'name': 'Versiones del manual',
            'source_type': 'text',
            'source_text': 'La entrega estándar tarda cinco días.',
        })
        self.assertEqual(manual.version, 1)
        manual.action_index()
        manual.write({'source_text': 'La entrega estándar tarda tres días.'})
        self.assertEqual(manual.version, 2)
        self.assertEqual(manual.state, 'pending')
        self.assertTrue(manual.source_updated_at)

    def test_knowledge_context_exposes_source_version(self):
        manual = self.env['ai.knowledge.base'].create({
            'name': 'Fuente trazable', 'source_type': 'text',
            'source_text': 'La garantía cubre doce meses.',
            'keyword_tags': 'garantía',
        })
        manual.action_index()
        details = self.env['ai.knowledge.base'].get_sales_context_details(
            query='garantía')
        self.assertTrue(details['sources'])
        self.assertEqual(details['sources'][0]['version'], manual.version)

    def test_knowledge_does_not_send_unrelated_chunks(self):
        manual = self.env['ai.knowledge.base'].create({
            'name': 'Manual selectivo IA test', 'source_type': 'text',
            'source_text': 'Política de garantía: cubre 12 meses.\n\n'
                           + ('Relleno operativo. ' * 500)
                           + '\n\nContenido administrativo sin relación.',
        })
        manual.action_index()
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp', 'external_id': '573000000102',
        })
        context = manual.get_sales_context(channel, query='garantía')
        self.assertIn('12 meses', context)
        self.assertNotIn('Contenido administrativo sin relación', context)

    def test_knowledge_context_reads_live_product_data(self):
        if 'product.product' not in self.env:
            self.skipTest('Módulo de productos no instalado')
        product = self.env['product.product'].create({
            'name': 'Producto vivo IA test', 'default_code': 'IA-LIVE-01',
            'list_price': 37.5,
        })
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp', 'external_id': '573000000100',
        })
        context = self.env['ai.knowledge.base'].get_sales_context(
            channel, query='precio Producto vivo IA test')
        self.assertIn(product.display_name, context)
        self.assertIn('37.50', context)
        self.assertIn('Datos vivos de productos en Odoo', context)

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
        expected_count = len(campaign._get_target_partners())
        self.assertEqual(campaign.pending_count, expected_count)
        self.assertEqual(len(campaign.recipient_ids), expected_count)
        self.assertIn(partner, campaign.recipient_ids.partner_id)
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
        expected_count = len(campaign.recipient_ids)

        self.env['chatroom.campaign']._cron_process_campaigns()
        self.assertEqual(campaign.state, 'sending', "todavía debe cerrar en la próxima corrida")
        self.assertEqual(campaign.failed_count, expected_count)
        self.assertEqual(campaign.pending_count, 0)

        self.env['chatroom.campaign']._cron_process_campaigns()
        self.assertEqual(campaign.state, 'sent')
        self.assertEqual(campaign.sent_count, 0)
        self.assertEqual(campaign.failed_count, expected_count)
        self.assertTrue(campaign.sent_date)
        campaign.action_retry_failed()
        self.assertEqual(campaign.state, 'sending')
        self.assertEqual(campaign.pending_count, expected_count)

    def test_campaign_cron_respects_batch_size(self):
        """Con batch_size=2 y 3 destinatarios, la primera corrida procesa
        solo 2 (deja 1 pendiente y sigue en 'sending')."""
        self.env['ir.config_parameter'].sudo().set_param('chatroom_whatsapp.access_token', False)
        self.env['ir.config_parameter'].sudo().set_param('chatroom_whatsapp.phone_number_id', False)
        category = self.env['crm.rfm.segment'].create({
            'name': 'Categoría técnica de lote', 'code': 'test_batch_unique',
            'definition_type': 'category', 'score_min': 0, 'score_max': 100,
        })
        for i in range(3):
            partner = self.env['res.partner'].create({
                'name': f"Cliente Lote {i}", 'phone': f"+57300210000{i}"})
            partner.rfm_category = category.code
        campaign = self.env['chatroom.campaign'].create({
            'name': "Campaña con lotes",
            'template_id': self.env['chatroom.template'].create({
                'name': 'test_campaign_template_5', 'language': 'es', 'body': "Hola.",
                'status': 'approved',
            }).id,
            'target_rfm_a': False, 'target_category_ids': [(6, 0, category.ids)], 'batch_size': 2,
        })
        campaign.action_send()
        expected_count = len(campaign.recipient_ids)
        self.assertEqual(campaign.pending_count, expected_count)

        self.env['chatroom.campaign']._cron_process_campaigns()
        self.assertEqual(campaign.state, 'sending')
        self.assertEqual(campaign.failed_count, 2)
        self.assertEqual(campaign.pending_count, expected_count - 2)

        self.env['chatroom.campaign']._cron_process_campaigns()
        self.assertEqual(campaign.state, 'sending')
        self.assertEqual(campaign.failed_count, expected_count)
        self.assertEqual(campaign.pending_count, 0)

        self.env['chatroom.campaign']._cron_process_campaigns()
        self.assertEqual(campaign.state, 'sent')

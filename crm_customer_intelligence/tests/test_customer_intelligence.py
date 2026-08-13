# -*- coding: utf-8 -*-
import base64
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.fields import Datetime
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestCrmCustomerIntelligence(TransactionCase):

    def _create_posted_invoice(self, partner, product, price, invoice_date):
        country = self.env['res.country'].search([('code', '=', 'EC')], limit=1)
        document_type = self.env['l10n_latam.document.type'].search([
            ('country_id', '=', country.id), ('code', '=', '01')], limit=1)
        # La base de pruebas usa la localización ecuatoriana: una factura
        # publicada debe tener identificación, país y tipo de documento.
        partner.write({
            'vat': partner.vat or '9999999999999',
            'country_id': partner.country_id.id or country.id,
        })
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': partner.id,
            'invoice_date': invoice_date,
            'l10n_latam_document_type_id': document_type.id,
            'l10n_latam_document_number': '001-001-%09d' % (
                partner.id * 100 + len(partner.invoice_ids) + 1),
            'invoice_line_ids': [(0, 0, {
                'product_id': product.id,
                'quantity': 1,
                'price_unit': price,
                'tax_ids': [(6, 0, [])],
            })],
        })
        invoice.action_post()
        return invoice

    def test_management_alert_state_red_for_stale_lead(self):
        """Una oportunidad sin gestión hace más de 15 días debe quedar en rojo."""
        partner = self.env['res.partner'].create({'name': "Cliente Estancado"})
        lead = self.env['crm.lead'].create({'name': "Oportunidad vieja", 'partner_id': partner.id})
        lead.write({'date_last_stage_update': Datetime.now() - timedelta(days=20)})

        self.assertEqual(lead.management_alert_state, 'red')
        self.assertGreaterEqual(lead.days_since_last_management, 15)

    def test_management_alert_state_green_for_fresh_lead(self):
        partner = self.env['res.partner'].create({'name': "Cliente Fresco"})
        lead = self.env['crm.lead'].create({'name': "Oportunidad nueva", 'partner_id': partner.id})

        self.assertEqual(lead.management_alert_state, 'green')

    def test_top_products_pareto_percentage(self):
        partner = self.env['res.partner'].create({'name': "Cliente Pareto"})
        product_a = self.env['product.product'].create({'name': "Producto Estrella", 'type': 'consu'})
        product_b = self.env['product.product'].create({'name': "Producto Secundario", 'type': 'consu'})
        self._create_posted_invoice(partner, product_a, 300.0, '2024-01-10')
        self._create_posted_invoice(partner, product_b, 100.0, '2024-01-11')

        top = partner._get_top_products(limit=5)

        self.assertEqual(top[0]['product_name'], "Producto Estrella")
        self.assertEqual(top[0]['percentage'], 75.0)
        self.assertIn("Producto Estrella", partner.commercial_top_product_summary)

    def test_commercial_metrics_only_counts_posted_invoices(self):
        partner = self.env['res.partner'].create({'name': "Cliente Métricas"})
        product = self.env['product.product'].create({'name': "Producto Métrica", 'type': 'consu'})
        country = self.env['res.country'].search([('code', '=', 'EC')], limit=1)
        document_type = self.env['l10n_latam.document.type'].search([
            ('country_id', '=', country.id), ('code', '=', '01')], limit=1)
        draft_invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': partner.id,
            'invoice_date': '2024-01-01',
            'l10n_latam_document_type_id': document_type.id,
            'l10n_latam_document_number': '001-001-000000999',
            'invoice_line_ids': [(0, 0, {'product_id': product.id, 'quantity': 1, 'price_unit': 50.0})],
        })
        self._create_posted_invoice(partner, product, 200.0, '2024-02-01')

        self.assertEqual(partner.commercial_invoice_count, 1)
        self.assertEqual(partner.commercial_total_sales, 200.0)
        self.assertNotEqual(draft_invoice.state, 'posted')

    def test_stagnant_lead_notifies_owner_once(self):
        salesperson = self.env['res.users'].create({
            'name': "Vendedor Test", 'login': 'vendedor_test_stagnant',
            'email': 'vendedor_test_stagnant@example.com',
        })
        partner = self.env['res.partner'].create({'name': "Cliente Estancado 2"})
        lead = self.env['crm.lead'].create({
            'name': "Oportunidad para notificar", 'partner_id': partner.id, 'user_id': salesperson.id,
        })
        lead.write({'date_last_stage_update': Datetime.now() - timedelta(days=20)})
        messages_before = len(lead.message_ids)

        self.env['crm.lead']._cron_notify_stagnant_leads()
        self.assertTrue(lead.stagnation_alert_notified)
        self.assertGreater(len(lead.message_ids), messages_before)

        messages_after_first_run = len(lead.message_ids)
        self.env['crm.lead']._cron_notify_stagnant_leads()
        self.assertEqual(len(lead.message_ids), messages_after_first_run,
                          "no debe mandar un segundo aviso mientras siga en rojo sin gestión nueva")

        lead.write({'date_last_stage_update': Datetime.now()})
        self.env['crm.lead']._cron_notify_stagnant_leads()
        self.assertFalse(lead.stagnation_alert_notified)

    def test_create_rfm_marketing_list(self):
        partner = self.env['res.partner'].create({
            'name': "Cliente Marketing", 'email': 'cliente.marketing@example.com'})
        partner.rfm_category = 'a'

        if 'mailing.list' not in self.env:
            with self.assertRaises(UserError):
                partner.action_create_rfm_marketing_list()
            return

        action = partner.action_create_rfm_marketing_list()
        mailing_list = self.env['mailing.list'].browse(action['res_id'])
        self.assertIn(partner.email, mailing_list.contact_ids.mapped('email'))

    def test_create_rfm_marketing_list_requires_email(self):
        partner = self.env['res.partner'].create({'name': "Cliente Sin Email"})
        with self.assertRaises(UserError):
            partner.action_create_rfm_marketing_list()

    def test_rfm_cron_classifies_top_spender_as_a(self):
        product = self.env['product.product'].create({'name': "Producto RFM", 'type': 'consu'})
        big_partner = self.env['res.partner'].create({'name': "Comprador Grande"})
        small_partner = self.env['res.partner'].create({'name': "Comprador Chico"})
        self._create_posted_invoice(big_partner, product, 10000.0, Datetime.now())
        self._create_posted_invoice(small_partner, product, 10.0, '2020-01-01')

        self.env['res.partner']._cron_compute_rfm_scores()

        self.assertEqual(big_partner.rfm_category, 'a')
        self.assertGreater(big_partner.rfm_score, small_partner.rfm_score)
        self.assertEqual(big_partner.rfm_frequency, 1)
        self.assertEqual(big_partner.rfm_monetary_value, 10000.0)
        self.assertTrue(big_partner.rfm_explanation)
        csv_action = self.env['res.partner'].action_export_rfm_dashboard_csv('all', 'all')
        self.assertIn('/web/content/', csv_action['url'])

    def test_rfm_cron_clears_stale_customer_values(self):
        partner = self.env['res.partner'].create({'name': "Cliente sin compras"})
        partner.write({
            'rfm_score': 88,
            'rfm_category': 'a',
            'rfm_frequency': 3,
            'rfm_monetary_value': 450.0,
        })

        self.env['res.partner']._cron_compute_rfm_scores()

        self.assertEqual(partner.rfm_score, 0)
        self.assertEqual(partner.rfm_category, 'none')
        self.assertEqual(partner.rfm_frequency, 0)
        self.assertEqual(partner.rfm_monetary_value, 0.0)

    def test_rfm_dashboard_comparison_includes_approved_history(self):
        historical_date = fields.Date.add(fields.Date.context_today(self), days=-120)
        csv_text = (
            'Nombre Cliente,RUC,Número Factura,Fecha Factura,Monto,Moneda\n'
            'Cliente comparación,999999999991,HIST-COMP,%s,250,USD\n'
        ) % fields.Date.to_string(historical_date)
        batch = self.env['crm.customer.history.batch'].create({
            'name': 'Comparación histórica',
            'file_name': 'comparison.csv',
            'file_data': base64.b64encode(csv_text.encode()),
        })
        batch.action_import_file()
        batch.action_approve()

        dashboard = self.env['res.partner'].get_rfm_dashboard_data('90', 'all')

        self.assertEqual(dashboard['comparison']['previous_sales'], 250.0)
        self.assertEqual(dashboard['comparison']['previous_invoice_count'], 1)

# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo.fields import Datetime
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestCrmCustomerIntelligence(TransactionCase):

    def _create_posted_invoice(self, partner, product, price, invoice_date):
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': partner.id,
            'invoice_date': invoice_date,
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
        draft_invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': partner.id,
            'invoice_line_ids': [(0, 0, {'product_id': product.id, 'quantity': 1, 'price_unit': 50.0})],
        })
        self._create_posted_invoice(partner, product, 200.0, '2024-02-01')

        self.assertEqual(partner.commercial_invoice_count, 1)
        self.assertEqual(partner.commercial_total_sales, 200.0)
        self.assertNotEqual(draft_invoice.state, 'posted')

    def test_rfm_cron_classifies_top_spender_as_a(self):
        product = self.env['product.product'].create({'name': "Producto RFM", 'type': 'consu'})
        big_partner = self.env['res.partner'].create({'name': "Comprador Grande"})
        small_partner = self.env['res.partner'].create({'name': "Comprador Chico"})
        self._create_posted_invoice(big_partner, product, 10000.0, Datetime.now())
        self._create_posted_invoice(small_partner, product, 10.0, '2020-01-01')

        self.env['res.partner']._cron_compute_rfm_scores()

        self.assertEqual(big_partner.rfm_category, 'a')
        self.assertGreater(big_partner.rfm_score, small_partner.rfm_score)

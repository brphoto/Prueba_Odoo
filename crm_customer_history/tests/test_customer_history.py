import base64

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestCustomerHistory(TransactionCase):

    def test_import_approve_and_feed_rfm(self):
        csv_text = (
            'Nombre Cliente,RUC,Número Factura,Fecha Factura,Monto,Moneda\n'
            'Cliente histórico test,999999999996,HIST-001,2024-01-10,200,USD\n'
        )
        batch = self.env['crm.customer.history.batch'].create({
            'name': 'Prueba histórico',
            'file_name': 'history.csv',
            'file_data': base64.b64encode(csv_text.encode()),
        })
        batch.action_import_file()
        self.assertEqual(batch.valid_count, 1)
        export_action = batch.action_export_csv()
        self.assertIn('/web/content/', export_action['url'])
        batch.action_approve()
        self.assertEqual(batch.state, 'approved')
        partner = batch.line_ids.partner_id
        rows = self.env['res.partner']._get_rfm_external_rows()
        self.assertEqual(rows[partner.id]['total'], 200.0)
        self.assertEqual(batch.approved_by, self.env.user)
        self.assertTrue(batch.approved_at)
        batch.action_revert_approval()
        self.assertEqual(batch.state, 'cancelled')
        self.assertFalse(self.env['res.partner']._get_rfm_external_rows().get(partner.id))

    def test_duplicate_rows_are_detected(self):
        csv_text = (
            'Cliente,RUC,Factura,Fecha,Monto\n'
            'Cliente duplicado test,999999999995,DUP-001,2024-01-10,50\n'
            'Cliente duplicado test,999999999995,DUP-001,2024-01-10,50\n'
        )
        batch = self.env['crm.customer.history.batch'].create({
            'name': 'Prueba duplicados',
            'file_name': 'duplicates.csv',
            'file_data': base64.b64encode(csv_text.encode()),
        })
        batch.action_import_file()
        self.assertEqual(batch.valid_count, 1)
        self.assertEqual(batch.duplicate_count, 1)

    def test_manual_category_keeps_audit_trace(self):
        partner = self.env['res.partner'].create({
            'name': 'Cliente con categoría manual',
            'rfm_category': 'b',
        })
        category = self.env['crm.rfm.segment'].search([
            ('definition_type', '=', 'category'), ('code', '=', 'a')], limit=1)
        partner.write({'history_manual_category_id': category.id})

        self.assertEqual(partner.history_manual_category_changed_by, self.env.user)
        self.assertEqual(partner.history_manual_category_previous, 'b')
        self.assertTrue(partner.history_manual_category_date)

        partner.write({'history_manual_category_id': False})
        self.assertFalse(partner.history_manual_category_changed_by)
        self.assertFalse(partner.history_manual_category_previous)

    def test_invalid_amount_is_reported_instead_of_breaking_import(self):
        csv_text = (
            'Cliente,RUC,Factura,Fecha,Monto\n'
            'Cliente monto inválido,999999999994,ERR-001,2024-01-10,0\n'
        )
        batch = self.env['crm.customer.history.batch'].create({
            'name': 'Prueba monto inválido',
            'file_name': 'invalid_amount.csv',
            'file_data': base64.b64encode(csv_text.encode()),
        })
        batch.action_import_file()

        self.assertEqual(batch.error_count, 1)
        self.assertIn('mayor que cero', batch.line_ids.error_message)

    def test_reactivation_uses_historical_last_purchase(self):
        from odoo import fields

        old_date = fields.Date.add(fields.Date.context_today(self), days=-120)
        csv_text = (
            'Cliente,RUC,Factura,Fecha,Monto\n'
            'Cliente reactivación,999999999993,REACT-001,%s,80\n'
        ) % fields.Date.to_string(old_date)
        batch = self.env['crm.customer.history.batch'].create({
            'name': 'Histórico reactivación',
            'file_name': 'reactivation.csv',
            'file_data': base64.b64encode(csv_text.encode()),
        })
        batch.action_import_file()
        batch.action_approve()
        partner = batch.line_ids.partner_id
        rule = self.env['rfm.reactivation.rule'].create({
            'name': 'Regla histórica de prueba',
            'category_code': partner.rfm_category,
            'days_allowed': 30,
        })

        created = rule._cron_process_reactivation()

        self.assertEqual(created, 1)
        self.assertTrue(self.env['crm.lead'].search([
            ('partner_id', '=', partner.id),
        ], limit=1))

    def test_unmatched_row_can_use_a_single_suggested_partner(self):
        csv_text = (
            'Cliente,RUC,Factura,Fecha,Monto\n'
            'Cliente sugerido,999999999992,SUG-001,2024-01-10,40\n'
        )
        batch = self.env['crm.customer.history.batch'].create({
            'name': 'Prueba sugerencias',
            'file_name': 'suggestions.csv',
            'create_missing_partners': False,
            'file_data': base64.b64encode(csv_text.encode()),
        })
        batch.action_import_file()
        partner = self.env['res.partner'].create({
            'name': 'Cliente sugerido', 'vat': '999999999992',
        })
        line = batch.line_ids
        self.assertIn(partner, line.suggested_partner_ids)
        line.action_use_suggested_partner()
        self.assertEqual(line.partner_id, partner)
        self.assertEqual(line.state, 'valid')

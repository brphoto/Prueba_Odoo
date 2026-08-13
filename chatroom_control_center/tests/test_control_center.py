from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestChatroomControlCenter(TransactionCase):

    def test_operational_metrics_have_popup_actions(self):
        center = self.env['chatroom.control.center'].create({})

        self.assertGreaterEqual(center.opportunity_count, 0)
        self.assertGreaterEqual(center.sales_order_count, 0)
        self.assertGreaterEqual(center.purchase_order_count, 0)
        self.assertGreaterEqual(center.invoice_count, 0)
        self.assertEqual(center.action_open_opportunities()['target'], 'new')
        self.assertEqual(center.action_open_sales_orders()['target'], 'new')
        self.assertEqual(center.action_open_invoices()['target'], 'new')

    def test_operational_actions_include_list_and_form_views(self):
        center = self.env['chatroom.control.center'].create({})
        action = center.action_open_open_conversations()

        self.assertEqual(action['views'], [(False, 'list'), (False, 'form')])
        self.assertEqual(action['domain'], [('state', 'in', ('open', 'pending'))])

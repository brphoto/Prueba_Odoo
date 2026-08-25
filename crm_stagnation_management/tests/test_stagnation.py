# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestCrmStagnationManagement(TransactionCase):

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.stage = self.env['crm.stage'].create({
            'name': 'Etapa prueba estancamiento',
            'stagnation_max_days': 10,
            'stagnation_required_activities': 1,
        })
        self.lead = self.env['crm.lead'].create({
            'name': 'Oportunidad estancada de prueba',
            'type': 'opportunity',
            'stage_id': self.stage.id,
            'expected_revenue': 1000,
            'user_id': self.env.user.id,
        })

    def test_stagnation_calculation_is_parametrizable(self):
        self.lead.write({'date_last_stage_update': fields.Datetime.now() - timedelta(days=8)})
        self.lead._recompute_stagnation_values()
        self.assertEqual(self.lead.stagnation_score, 'warning')
        self.assertEqual(self.lead.purge_recommendation, 'push')
        self.assertEqual(self.lead.estimated_capital_trapped, 300)

        self.stage.write({'stagnation_max_days': 5})
        self.lead._recompute_stagnation_values()
        self.assertEqual(self.lead.stagnation_score, 'stagnant')

    def test_wizard_requires_human_decision_data(self):
        self.lead.write({
            'stagnation_score': 'stagnant',
            'real_vs_fake_score': 10,
            'estimated_capital_trapped': 500,
        })
        wizard = self.env['crm.lead.purge.wizard'].create({
            'stagnation_filter': 'manual',
            'selected_lead_ids': [(6, 0, self.lead.ids)],
            'action': 'assign_review',
            'create_activities': False,
            'notify_owners': False,
        })
        with self.assertRaises(UserError):
            wizard.action_execute_purge()
        manager = self.env.ref('base.user_admin')
        wizard.reviewer_id = manager.id
        wizard.with_user(manager).action_execute_purge()
        self.assertEqual(self.lead.user_id, manager)

    def test_default_configuration_is_created_per_company(self):
        config = self.env['crm.stagnation.config'].get_for_company(self.company)
        self.assertEqual(config.default_max_days, 30)
        self.assertEqual(config.notification_level, 'critical')
        self.assertTrue(config.notify_enabled)

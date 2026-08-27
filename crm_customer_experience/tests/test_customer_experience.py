# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase


class TestCustomerExperience(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Prueba NPS Cliente'})
        cls.response_model = cls.env['crm.nps.response']

    def test_nps_categories_and_partner_summary(self):
        baseline_total = self.response_model.search_count([])
        baseline_promoters = self.response_model.search_count([('category', '=', 'promoter')])
        baseline_detractors = self.response_model.search_count([('category', '=', 'detractor')])
        response = self.response_model.create({'partner_id': self.partner.id, 'score': 10, 'reason': 'Excelente atención'})
        self.assertEqual(response.category, 'promoter')
        self.partner.invalidate_recordset()
        self.assertEqual(self.partner.nps_score, 10)
        self.assertEqual(self.partner.nps_category, 'promoter')
        expected_nps = ((baseline_promoters + 1 - baseline_detractors) /
                        (baseline_total + 1) * 100.0)
        self.assertEqual(self.response_model.global_nps(), expected_nps)

    def test_nps_boundaries(self):
        detractor = self.response_model.create({'partner_id': self.partner.id, 'score': 6})
        passive = self.response_model.create({'partner_id': self.partner.id, 'score': 8})
        self.assertEqual(detractor.category, 'detractor')
        self.assertEqual(passive.category, 'passive')

    def test_snapshot_can_refresh_without_sales(self):
        self.env['crm.experience.snapshot']._refresh_today()
        snapshot = self.env['crm.experience.snapshot'].search([], order='id desc', limit=1)
        self.assertTrue(snapshot)
        self.assertGreaterEqual(snapshot.response_count, 0)

    def test_native_survey_is_imported_as_nps(self):
        survey = self.env.ref('crm_customer_experience.survey_nps')
        question = self.env.ref('crm_customer_experience.survey_nps_score')
        user_input = self.env['survey.user_input'].create({
            'survey_id': survey.id, 'partner_id': self.partner.id,
        })
        self.env['survey.user_input.line'].create({
            'user_input_id': user_input.id, 'question_id': question.id,
            'answer_type': 'scale', 'value_scale': 9,
        })
        user_input.write({'state': 'done'})
        self.assertEqual(user_input.nps_response_id.score, 9)
        self.assertEqual(user_input.nps_response_id.category, 'promoter')

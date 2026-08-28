# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase


class TestNpsCampaign(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.survey = cls.env.ref('crm_customer_experience.survey_nps')
        cls.category = cls.env['crm.rfm.segment'].create({
            'name': 'Categoría de prueba NPS',
            'definition_type': 'category',
            'code': 'test_nps_category',
            'score_min': 0,
            'score_max': 100,
        })
        cls.partner = cls.env['res.partner'].create({
            'name': 'Cliente de prueba campaña NPS',
            'customer_rank': 1,
            'email': 'nps-campaign@example.test',
            'rfm_category': cls.category.code,
        })

    def test_queue_creates_individual_survey_link(self):
        campaign = self.env['crm.nps.campaign'].create({
            'name': 'Prueba campaña NPS por categoría',
            'survey_id': self.survey.id,
            'target_category_ids': [(6, 0, self.category.ids)],
            'channel': 'email',
            'exclude_answered_days': 0,
        })
        self.assertEqual(campaign.audience_count, 1)
        campaign.action_queue()
        self.assertEqual(campaign.state, 'queued')
        self.assertEqual(len(campaign.recipient_ids), 1)
        self.assertIn('answer_token=', campaign.recipient_ids.survey_url)

    def test_survey_response_updates_campaign_recipient(self):
        campaign = self.env['crm.nps.campaign'].create({
            'name': 'Prueba trazabilidad NPS',
            'survey_id': self.survey.id,
            'target_category_ids': [(6, 0, self.category.ids)],
            'channel': 'email',
            'exclude_answered_days': 0,
        })
        campaign.action_queue()
        recipient = campaign.recipient_ids[:1]
        question = self.env.ref('crm_customer_experience.survey_nps_score')
        self.env['survey.user_input.line'].create({
            'user_input_id': recipient.survey_user_input_id.id,
            'question_id': question.id,
            'answer_type': 'scale',
            'value_scale': 10,
        })
        recipient.survey_user_input_id.write({'state': 'done'})
        self.assertEqual(recipient.response_id.score, 10)
        self.assertEqual(recipient.partner_id.nps_category, 'promoter')

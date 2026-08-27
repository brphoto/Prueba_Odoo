# -*- coding: utf-8 -*-
from odoo import fields, models


class SurveyUserInput(models.Model):
    _inherit = 'survey.user_input'

    nps_response_id = fields.Many2one('crm.nps.response', string='Registro NPS', readonly=True, copy=False)

    def write(self, vals):
        result = super().write(vals)
        completed = self.filtered(lambda item: item.state == 'done' and not item.test_entry and not item.nps_response_id)
        survey = self.env.ref('crm_customer_experience.survey_nps', raise_if_not_found=False)
        if survey:
            for user_input in completed.filtered(lambda item: item.survey_id == survey and item.partner_id):
                scale = user_input.user_input_line_ids.filtered(
                    lambda line: line.question_id.question_type == 'scale' and not line.skipped)[:1]
                if not scale:
                    continue
                reason = user_input.user_input_line_ids.filtered(
                    lambda line: line.question_id.question_type == 'text_box' and not line.skipped)[:1]
                response = self.env['crm.nps.response'].create({
                    'partner_id': user_input.partner_id.id, 'score': scale.value_scale,
                    'reason': reason.value_text_box if reason else False,
                    'response_date': fields.Date.to_date(user_input.end_datetime) if user_input.end_datetime else fields.Date.context_today(self),
                    'survey_user_input_id': user_input.id, 'source': 'survey',
                })
                user_input.nps_response_id = response.id
        return result

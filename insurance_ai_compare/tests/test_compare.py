# -*- coding: utf-8 -*-
"""Comparativo de cotizaciones: lectura, puntaje, análisis, PDF, envío y póliza."""
import json
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged
from odoo.tools import mute_logger

from ..models.insurance_compare import to_number
from .common import EXTRACTIONS, InsuranceCompareCase, fake_complete_factory, make_pdf


@tagged('post_install', '-at_install')
class TestInsuranceCompare(InsuranceCompareCase):

    def _service_patch(self, **kwargs):
        return patch.object(type(self.env['chatroom.ai.service']), 'complete',
                            fake_complete_factory(**kwargs))

    def _extracted_compare(self, **kwargs):
        compare = self._compare(**kwargs)
        with self._service_patch():
            compare.action_extract()
            self.env['insurance.compare']._cron_process_offers(limit=10)
        return compare

    # -- Servicio de IA y documentos ------------------------------------

    def test_pdf_pages_are_read_page_by_page(self):
        pages = self.env['chatroom.ai.service'].extract_pdf_pages(
            make_pdf(['Prima total: 920,00', 'Responsabilidad civil 30.000']))
        self.assertEqual(len(pages), 1)
        self.assertIn('Prima total', pages[0])

    def test_documents_are_wrapped_as_data(self):
        service = self.env['chatroom.ai.service']
        wrapped = service.wrap_document('cot"<x>.pdf', ['uno', '', 'tres'])
        self.assertIn('<documento nombre="cotx.pdf">', wrapped)
        self.assertIn('[página 1]', wrapped)
        self.assertIn('[página 3]', wrapped)
        self.assertNotIn('[página 2]', wrapped)
        self.assertIn('nunca instrucciones', service.document_guard())

    def test_invalid_json_is_retried_with_the_error(self):
        answers = iter(['esto no es json', '```json\n{"a": 1, "b": 2}\n```'])
        received = []

        def fake(channel, messages, task_type=None, model_id=None):
            received.append(messages)
            return next(answers)

        with patch.object(type(self.env['chatroom.channel']), '_ai_chat_completion', fake):
            data = self.env['chatroom.ai.service'].complete_json(
                [{'role': 'user', 'content': 'dame json'}], required_keys=('a',))
        self.assertEqual(data, {'a': 1, 'b': 2})
        self.assertIn('no contiene un objeto JSON', received[1][-1]['content'])

    def test_json_without_required_keys_fails_clearly(self):
        with patch.object(type(self.env['chatroom.channel']), '_ai_chat_completion',
                          lambda *args, **kwargs: '{"otra": 1}'):
            with self.assertRaisesRegex(UserError, 'faltan las claves'):
                self.env['chatroom.ai.service'].complete_json(
                    [{'role': 'user', 'content': 'x'}], required_keys=('a',))

    def test_amounts_written_in_any_format(self):
        cases = {'$ 1.234,56': 1234.56, '1,234.56': 1234.56, 'USD 850': 850.0, '850,50': 850.5,
                 '18.500': 18500.0, '0.75': 0.75, 'sin dato': None, None: None}
        for raw, expected in cases.items():
            self.assertEqual(to_number(raw), expected, raw)

    # -- Flujo completo -------------------------------------------------

    def test_full_flow_from_pdfs_to_policy(self):
        compare = self._extracted_compare()
        self.assertEqual(compare.state, 'review')
        norte, sur, oeste = (compare.offer_ids.filtered(lambda o, n=name: o.insurer_id.name == n)
                             for name in self.insurers)
        # Lectura: montos normalizados y coberturas ubicadas en el catálogo por sinónimo.
        self.assertEqual(norte.premium_total, 920.0)
        self.assertEqual(norte.sum_insured, 18500.0)
        self.assertEqual(norte.deductible_amount, 250.0)
        rc = self.env.ref('insurance_ai_compare.cov_vehicles_rc')
        substitute = self.env.ref('insurance_ai_compare.cov_vehicles_sustituto')
        self.assertEqual(norte.line_ids.filtered(lambda l: l.name == 'Daños a terceros').coverage_id, rc)
        self.assertEqual(norte.line_ids.filtered(lambda l: l.name == 'Auto de reemplazo').coverage_id, substitute)
        self.assertEqual(norte.review_count, 1, 'La cobertura con confianza 0.6 queda por revisar.')
        # Puntaje calculado por Odoo: Oeste es la más barata pero no tiene RC (obligatoria).
        self.assertTrue(oeste.disqualified)
        self.assertIn('Responsabilidad civil', oeste.disqualified_reason)
        self.assertEqual(oeste.rank, 0)
        self.assertEqual(sorted((norte.rank, sur.rank)), [1, 2])
        self.assertEqual(compare.recommended_offer_id.rank, 1)
        self.assertIn('Aseguradora Norte QA', compare.matrix_html)
        self.assertIn('Descartada', compare.matrix_html)

        with self._service_patch():
            compare.action_analyze()
        self.assertEqual(compare.state, 'analyzed')
        self.assertEqual(compare.recommended_offer_id, norte)
        self.assertEqual(compare.ai_recommended_offer_id, norte)
        self.assertIn('Auto de reemplazo', norte.advantages)
        self.assertIn('Bajar el deducible', compare.negotiation_notes)
        self.assertIn('auto de reemplazo', compare.client_explanation)

        with self.assertRaisesRegex(UserError, 'Aprueba'):
            compare.action_send_whatsapp()
        compare.action_approve()
        self.assertEqual(compare.state, 'approved')
        self.assertEqual(compare.approved_by_id, self.env.user)

        Report = self.env['ir.actions.report']
        client_html = Report._render_qweb_html(
            'insurance_ai_compare.action_report_insurance_compare_client', compare.ids)[0].decode()
        internal_html = Report._render_qweb_html(
            'insurance_ai_compare.action_report_insurance_compare_internal', compare.ids)[0].decode()
        self.assertIn('Opción recomendada', client_html)
        self.assertNotIn('BORRADOR', client_html)
        self.assertNotIn('Bajar el deducible', client_html, 'La negociación no va al cliente.')
        self.assertIn('Bajar el deducible', internal_html)

        sent = []
        with patch.object(type(self.env['chatroom.channel']), '_send_report_as_message',
                          lambda channel, report, res_id, filename: sent.append((report, res_id, filename))), \
                patch.object(type(self.env['chatroom.channel']), 'action_send_text', lambda *a, **k: True):
            compare.action_send_whatsapp()
        self.assertEqual(sent[0][0], 'insurance_ai_compare.action_report_insurance_compare_client')
        self.assertEqual(compare.state, 'sent')
        self.assertEqual(compare.channel_id.partner_id, self.partner)

        wizard = self.env['insurance.policy.wizard'].with_context(
            default_compare_id=compare.id, default_offer_id=norte.id).create({
                'numero_poliza': 'POL-QA-001',
                'executive_id': self.env['polizas.ramos'].create({'name': 'Ejecutivo QA'}).id,
                'poliza_type_id': self.env['poliza.type'].create({'name': 'Individual QA'}).id,
            })
        self.assertEqual(wizard.coverage_count, 3)
        wizard.action_confirm()
        policy = compare.policy_id
        self.assertEqual(compare.state, 'won')
        self.assertEqual(policy.aseguradora_id, norte.insurer_id)
        self.assertEqual(policy.prima_total, 920.0)
        self.assertEqual(len(policy.cobertura_ids), 3)
        self.assertIn('Responsabilidad civil', policy.cobertura_ids.mapped('name'))

    def test_draft_pdf_is_marked_as_draft(self):
        compare = self._extracted_compare()
        html = self.env['ir.actions.report']._render_qweb_html(
            'insurance_ai_compare.action_report_insurance_compare_client', compare.ids)[0].decode()
        self.assertIn('BORRADOR', html)

    def test_ai_cannot_recommend_a_disqualified_offer(self):
        compare = self._extracted_compare()
        analysis = {'recomendacion': {'aseguradora': 'Aseguradora Oeste QA', 'motivo': 'Es la más barata.'},
                    'ofertas': []}
        with self._service_patch(analysis=analysis):
            compare.action_analyze()
        self.assertNotEqual(compare.recommended_offer_id.insurer_id.name, 'Aseguradora Oeste QA')
        self.assertIn('descartada', compare.recommendation_reason)

    def test_one_failing_document_does_not_stop_the_others(self):
        compare = self._compare()
        extractions = dict(EXTRACTIONS, **{'Aseguradora Sur QA': UserError('PDF ilegible')})
        with patch.object(type(self.env['chatroom.ai.service']), 'complete',
                          fake_complete_factory(extractions=extractions)), \
                mute_logger('odoo.addons.insurance_ai_compare.models.insurance_compare'):
            compare.action_extract()
            self.env['insurance.compare']._cron_process_offers(limit=10)
        sur = compare.offer_ids.filtered(lambda o: o.insurer_id.name == 'Aseguradora Sur QA')
        self.assertEqual(sur.state, 'error')
        self.assertIn('PDF ilegible', sur.error_message)
        self.assertEqual(compare.state, 'review')
        self.assertEqual(len(compare.offer_ids.filtered(lambda o: o.state == 'extracted')), 2)

    def test_scanned_pdf_without_text_asks_for_manual_data(self):
        compare = self._compare(insurers=['Aseguradora Norte QA'])
        compare.offer_ids.document = make_pdf([])
        with self._service_patch(), \
                patch.object(type(self.env['chatroom.ai.service']), '_pdf_pages_ocr',
                             staticmethod(lambda raw: [])), \
                mute_logger('odoo.addons.insurance_ai_compare.models.insurance_compare'):
            compare.action_extract()
            self.env['insurance.compare']._cron_process_offers(limit=10)
        self.assertEqual(compare.offer_ids.state, 'error')
        self.assertIn('a mano', compare.offer_ids.error_message)
        compare.offer_ids.action_mark_manual()
        self.assertEqual(compare.state, 'review')

    def test_human_corrections_count_as_reviewed(self):
        compare = self._extracted_compare()
        line = compare.offer_ids.line_ids.filtered('needs_review')[:1]
        self.assertFalse(line.reviewed)
        line.state = 'limited'
        self.assertTrue(line.reviewed)

    def test_analysis_needs_two_offers(self):
        compare = self._extracted_compare(insurers=['Aseguradora Norte QA'])
        with self.assertRaisesRegex(UserError, 'dos cotizaciones'):
            compare.action_analyze()

    # -- LOPDP y seguridad ----------------------------------------------

    def test_consent_is_required_before_using_ai(self):
        partner = self.env['res.partner'].create({'name': 'Sin consentimiento QA'})
        compare = self._compare(partner=partner)
        self.assertFalse(compare.consent_ok)
        with self.assertRaisesRegex(UserError, 'LOPDP'):
            compare.action_extract()
        action = compare.action_register_consent()
        self.assertEqual(action['context']['default_partner_id'], partner.id)

    def test_portal_users_cannot_read_policies(self):
        portal = new_test_user(self.env, login='portal_polizas_qa', groups='base.group_portal')
        with self.assertRaises(AccessError):
            self.env['poliza.partner'].with_user(portal).search([])
        with self.assertRaises(AccessError):
            self.env['insurance.compare'].with_user(portal).search([])

    def test_advisor_can_work_but_not_configure(self):
        advisor = new_test_user(self.env, login='asesor_seguros_qa',
                                groups='insurance_ai_compare.group_insurance_compare_user')
        compare = self._compare()
        self.assertTrue(compare.with_user(advisor).read(['name']))
        with self.assertRaises(AccessError):
            self.template.with_user(advisor).write({'weight_price': 50})

    def test_ai_usage_is_recorded_without_conversation(self):
        if 'chatroom.ai.usage.event' not in self.env:
            self.skipTest('Sin registro de consumo instalado.')
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('chatroom_whatsapp.ai_enabled', 'True')
        icp.set_param('chatroom_whatsapp.ai_provider_url', 'https://ia.invalid/v1')
        icp.set_param('chatroom_whatsapp.ai_api_key', 'clave')

        class Response:
            status_code = 200

            @staticmethod
            def json():
                return {'choices': [{'message': {'content': '{"ok": true}'}}],
                        'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}}

        with patch.object(type(self.env['chatroom.channel']), '_meta_request',
                          lambda *args, **kwargs: Response()):
            data = self.env['chatroom.ai.service'].complete_json([{'role': 'user', 'content': 'x'}])
        self.assertEqual(data, {'ok': True})
        event = self.env['chatroom.ai.usage.event'].search([], order='id desc', limit=1)
        self.assertEqual(event.task_type, 'document')
        self.assertFalse(event.channel_id)
        self.assertEqual(event.total_tokens, 15)
        self.assertTrue(json.dumps(data))

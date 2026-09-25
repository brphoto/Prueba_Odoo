# -*- coding: utf-8 -*-
"""El comparativo en un navegador real."""
from unittest.mock import patch

from odoo.tests import HttpCase, tagged

from .common import fake_complete_factory, make_pdf


@tagged('post_install', '-at_install')
class TestInsuranceCompareTour(HttpCase):

    def test_compare_tour(self):
        env = self.env
        env['ir.config_parameter'].sudo().set_param('insurance_ai_compare.require_consent', 'True')
        partner = env['res.partner'].create({'name': 'Cliente Tour Seguros'})
        env['ec.data.consent'].create({
            'partner_id': partner.id, 'signed_by': 'Cliente Tour Seguros',
            'consent_type_id': env.ref('insurance_ai_compare.consent_type_asesoria_ia').id,
        })
        insurers = {name: env['polizas.aseguradoras'].create({'name': name})
                    for name in ('Aseguradora Norte QA', 'Aseguradora Sur QA', 'Aseguradora Oeste QA')}
        compare = env['insurance.compare'].create({
            'partner_id': partner.id,
            'template_id': env.ref('insurance_ai_compare.template_vehicles').id,
            'offer_ids': [(0, 0, {'insurer_id': insurer.id, 'document': make_pdf([name]),
                                  'document_name': '%s.pdf' % name})
                          for name, insurer in insurers.items()],
        })
        with patch.object(type(env['chatroom.ai.service']), 'complete', fake_complete_factory()):
            compare.action_extract()
            env['insurance.compare']._cron_process_offers(limit=10)
            compare.action_analyze()
        self.assertEqual(compare.state, 'analyzed')
        env.flush_all()
        self.start_tour('/odoo/action-insurance_ai_compare.action_insurance_compare',
                        'insurance_compare_tour', login='admin')
        self.assertEqual(compare.state, 'approved')

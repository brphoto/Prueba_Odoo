from datetime import datetime

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestMarketingLeadIntelligence(TransactionCase):
    """El módulo no tenía tests, y por eso nadie vio que el perfil de
    calidad reventaba al abrir una oportunidad sin teléfono propio."""

    def _social_context(self):
        account = self.env['marketing.social.account'].create({
            'name': 'QA cuenta lead intel', 'platform': 'instagram',
            'external_id': 'qa-lead-intel-001',
        })
        publication = self.env['marketing.social.publication'].create({
            'name': 'QA publicación lead intel', 'account_id': account.id,
            'published_at': datetime.combine(
                fields.Date.context_today(self), datetime.min.time()),
            'content_type': 'reel',
        })
        conversation = self.env['marketing.social.conversation'].create({
            'name': 'QA conversación lead intel', 'account_id': account.id,
            'external_id': 'qa-conv-lead-intel-001',
        })
        return account, publication, conversation

    def test_quality_score_without_phone_uses_the_partner_phone(self):
        """`res.partner.mobile` ya no existe en Odoo 19.

        El cálculo lo miraba dentro de un `or`, así que solo se evaluaba
        cuando el lead NO tenía teléfono: justo el caso en el que hacía
        falta. Abrir esa oportunidad lanzaba AttributeError.
        """
        partner = self.env['res.partner'].create({
            'name': 'QA contacto con teléfono', 'phone': '0991234567',
        })
        lead = self.env['crm.lead'].create({
            'name': 'QA oportunidad sin teléfono propio',
            'partner_id': partner.id,
        })
        # Basta con que leer el campo no explote.
        lead.invalidate_recordset()
        self.assertGreater(lead.marketing_quality_score, 0)
        # 20 (contacto) + 15 (teléfono del contacto) como mínimo.
        self.assertGreaterEqual(lead.marketing_quality_score, 35)

    def test_quality_score_without_any_phone_does_not_credit_the_points(self):
        partner = self.env['res.partner'].create({'name': 'QA contacto sin teléfono'})
        lead = self.env['crm.lead'].create({
            'name': 'QA sin ningún teléfono', 'partner_id': partner.id,
        })
        with_partner_only = lead.marketing_quality_score
        partner.phone = '0999999999'
        lead.invalidate_recordset()
        self.assertEqual(
            lead.marketing_quality_score, with_partner_only + 15,
            'El teléfono del contacto debería sumar sus puntos.')

    def test_social_counters_match_the_linked_records(self):
        """Los contadores agrupados devuelven lo mismo que contar a mano."""
        account, publication, conversation = self._social_context()
        for index in range(3):
            self.env['marketing.social.conversation.message'].create({
                'conversation_id': conversation.id,
                'external_id': 'qa-msg-lead-intel-%s' % index,
                'body': 'mensaje %s' % index,
                'direction': 'inbound',
                'message_at': datetime.combine(
                    fields.Date.context_today(self), datetime.min.time()),
            })
        for index in range(2):
            self.env['marketing.social.interaction'].create({
                'publication_id': publication.id, 'interaction_type': 'comment',
                'author_name': 'QA %s' % index, 'text': 'hola',
                'interaction_date': datetime.combine(
                    fields.Date.context_today(self), datetime.min.time()),
            })
        lead = self.env['crm.lead'].create({
            'name': 'QA lead con origen social',
            'marketing_account_id': account.id,
            'marketing_publication_id': publication.id,
            'marketing_conversation_id': conversation.id,
        })
        lead.invalidate_recordset()
        self.assertEqual(lead.marketing_message_count, 3)
        self.assertEqual(lead.marketing_interaction_count, 2)
        self.assertEqual(lead.marketing_platform, 'instagram')
        self.assertIn(publication.name, lead.marketing_attribution_note)

    def test_counters_are_zero_without_a_social_origin(self):
        lead = self.env['crm.lead'].create({'name': 'QA lead sin origen'})
        self.assertEqual(lead.marketing_message_count, 0)
        self.assertEqual(lead.marketing_interaction_count, 0)
        self.assertEqual(lead.marketing_attribution_note, 'Origen no atribuido')

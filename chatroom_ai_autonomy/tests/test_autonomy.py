# -*- coding: utf-8 -*-
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestChatroomAiAutonomy(TransactionCase):

    def test_knowledge_profile_sync_is_local(self):
        profile = self.env['chatroom.ai.knowledge.profile'].create({
            'name': 'QA perfil operativo',
        })
        self.assertTrue(profile.action_sync())
        self.assertEqual(profile.state, 'ready')
        self.assertGreaterEqual(profile.product_count, 0)
        self.assertIn('no consume tokens', profile.last_result)
        self.assertIn('Conocimiento local listo', profile.sync_guidance)

    def test_policy_decisions_cover_safe_modes(self):
        policy = self.env['chatroom.ai.autonomy.policy'].create({
            'name': 'QA política controlada',
            'mode': 'approval',
            'allow_order': True,
            'max_order_amount': 100,
        })
        approval = policy.evaluate('confirm_order', amount=20, confidence=0.95)
        blocked = policy.evaluate('send_payment_link', amount=20, confidence=0.95)
        over_limit = policy.evaluate('confirm_order', amount=200, confidence=0.95)
        self.assertEqual(approval['decision'], 'approval')
        self.assertEqual(blocked['decision'], 'blocked')
        self.assertEqual(over_limit['decision'], 'approval')

    def test_simulator_uses_live_knowledge_without_provider(self):
        simulator = self.env['chatroom.ai.autonomy.simulator'].create({
            'query': '¿Qué productos y precios tenemos disponibles?',
            'action_key': 'reply',
        })
        self.assertTrue(simulator.action_simulate())
        self.assertIn(simulator.decision, ('approval', 'allow'))
        self.assertTrue(simulator.request_id)
        self.assertGreaterEqual(simulator.estimated_tokens, 0)
        self.assertTrue(simulator.simulation_message)
        self.assertIn('simulación', simulator.simulation_message.lower())

    def test_active_policy_blocks_autonomous_checkout(self):
        partner = self.env.ref('base.partner_root')
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp',
            'external_id': 'autonomy-qa-%s' % self.env.user.id,
            'partner_id': partner.id,
        })
        policy = self.env['chatroom.ai.autonomy.policy'].create({
            'name': 'QA bloqueo checkout',
            'mode': 'autonomous',
            'allow_order': False,
            'active': True,
        })
        self.env['ir.config_parameter'].sudo().set_param('chatroom_ai_sales.auto_confirm', 'True')
        order = self.env['sale.order'].create({'partner_id': partner.id})
        channel._sales_after_checkout(order)
        self.assertEqual(channel.ai_sales_status, 'escalated')
        self.assertTrue(self.env['chatroom.ai.autonomy.request'].search_count([
            ('policy_id', '=', policy.id), ('channel_id', '=', channel.id),
        ]))

    def test_profile_filters_live_sources(self):
        profile = self.env['chatroom.ai.knowledge.profile'].create({
            'name': 'QA fuentes filtradas',
            'include_company': False,
            'include_products': False,
            'include_stock': False,
            'include_customer': True,
            'include_rfm': False,
        })
        profile.action_set_default()
        details = self.env['ai.knowledge.base'].get_sales_context_details(
            query='cliente', partner=self.env.ref('base.partner_root'), company=self.env.company)
        self.assertNotIn('Empresa y moneda', details['live_sources'])
        self.assertNotIn('Productos coincidentes de Odoo', details['live_sources'])
        self.assertNotIn('RFM del cliente', details['live_sources'])
        self.assertIn('Ficha del cliente', details['live_sources'])

    def test_template_renders_without_provider(self):
        partner = self.env.ref('base.partner_root')
        template = self.env['chatroom.ai.message.template'].create({
            'name': 'QA plantilla',
            'body': 'Hola {{partner_name}}, te escribimos desde {{company_name}}.',
        })
        rendered = template.render(partner=partner)
        self.assertIn(partner.name, rendered)
        self.assertIn(self.env.company.name, rendered)
        self.assertNotIn('{{partner_name}}', rendered)

    def test_memory_is_local_and_available_to_context(self):
        partner = self.env.ref('base.partner_root')
        memory = self.env['chatroom.ai.memory'].remember(
            'El cliente prefiere entregas en la mañana', partner=partner,
            source='conversation', memory_type='preference')
        self.assertTrue(memory)
        self.assertIn('mañana', self.env['chatroom.ai.memory'].get_context(partner=partner))

    def test_guided_setup_explains_operating_risk_before_apply(self):
        wizard = self.env['chatroom.ai.autonomy.setup'].create({})
        self.assertIn('aprobación humana', wizard.configuration_message)

        wizard.write({'mode': 'assist'})
        self.assertIn('Modo sugerencias', wizard.configuration_message)

        wizard.write({'mode': 'autonomous', 'allow_order': True, 'max_order_amount': 0})
        self.assertIn('sin límite monetario', wizard.configuration_message)

    def test_policy_exposes_operational_risk_summary(self):
        policy = self.env['chatroom.ai.autonomy.policy'].create({
            'name': 'QA resumen de riesgo',
            'mode': 'autonomous',
            'allow_order': True,
        })
        self.assertEqual(policy.risk_level, 'high')
        self.assertIn('acciones comerciales', policy.operational_summary)

        policy.write({'mode': 'assist', 'allow_order': False, 'allow_quotation': False})
        self.assertEqual(policy.risk_level, 'low')

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

    def test_policy_scope_prioritizes_channel_then_partner_then_global(self):
        partner = self.env.ref('base.partner_root')
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp',
            'external_id': 'autonomy-scope-%s' % self.env.user.id,
            'partner_id': partner.id,
        })
        global_policy = self.env['chatroom.ai.autonomy.policy'].create({
            'name': 'QA global', 'scope': 'global', 'mode': 'approval',
        })
        partner_policy = self.env['chatroom.ai.autonomy.policy'].create({
            'name': 'QA cliente', 'scope': 'partners', 'partner_ids': [(6, 0, [partner.id])],
            'mode': 'autonomous',
        })
        self.assertEqual(
            self.env['chatroom.ai.autonomy.policy'].get_active_policy(
                self.env.company, partner=partner), partner_policy)
        channel_policy = self.env['chatroom.ai.autonomy.policy'].create({
            'name': 'QA canal', 'scope': 'channels', 'channel_ids': [(6, 0, [channel.id])],
            'mode': 'autonomous', 'sequence': 99,
        })
        self.assertEqual(
            self.env['chatroom.ai.autonomy.policy'].get_active_policy(
                self.env.company, channel=channel, partner=partner), channel_policy)
        self.assertNotEqual(global_policy, channel_policy)

    def test_agent_task_is_released_only_by_autonomous_policy(self):
        partner = self.env.ref('base.partner_root')
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp',
            'external_id': 'autonomy-task-%s' % self.env.user.id,
            'partner_id': partner.id,
        })
        self.env['ir.config_parameter'].sudo().set_param('chatroom_ai_agent.mode', 'automatic')
        policy = self.env['chatroom.ai.autonomy.policy'].create({
            'name': 'QA tareas autónomas', 'mode': 'autonomous',
            'scope': 'channels', 'channel_ids': [(6, 0, [channel.id])],
            'allow_lead': True, 'allow_activity': True,
        })
        task = self.env['chatroom.ai.task'].create_from_channel(
            channel, task_type='qualify_lead', approval_required=False)
        task.action_plan()
        self.assertEqual(task.state, 'planned')
        self.assertEqual(task.autonomy_decision, 'allow')
        self.assertEqual(task.autonomy_policy_id, policy)
        self.assertFalse(task.action_ids.filtered(lambda action: action.key == 'create_lead').requires_approval)

    def test_agent_task_stays_pending_when_policy_requires_approval(self):
        partner = self.env.ref('base.partner_root')
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp',
            'external_id': 'autonomy-approval-%s' % self.env.user.id,
            'partner_id': partner.id,
        })
        self.env['ir.config_parameter'].sudo().set_param('chatroom_ai_agent.mode', 'automatic')
        self.env['chatroom.ai.autonomy.policy'].create({
            'name': 'QA requiere revisión', 'mode': 'approval',
            'scope': 'channels', 'channel_ids': [(6, 0, [channel.id])],
            'allow_lead': True,
        })
        task = self.env['chatroom.ai.task'].create_from_channel(
            channel, task_type='qualify_lead', approval_required=False)
        task.action_plan()
        self.assertEqual(task.state, 'awaiting_approval')
        self.assertEqual(task.autonomy_decision, 'approval')
        self.assertTrue(task.approval_required)
        self.assertTrue(self.env['chatroom.ai.autonomy.exception'].search_count([
            ('task_id', '=', task.id), ('state', '=', 'open'),
        ]))

    def test_autonomous_flow_can_continue_with_a_bounded_chain(self):
        partner = self.env.ref('base.partner_root')
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp',
            'external_id': 'autonomy-chain-%s' % self.env.user.id,
            'partner_id': partner.id,
        })
        self.env['ir.config_parameter'].sudo().set_param('chatroom_ai_agent.mode', 'automatic')
        policy = self.env['chatroom.ai.autonomy.policy'].create({
            'name': 'QA cadena limitada', 'mode': 'autonomous',
            'scope': 'channels', 'channel_ids': [(6, 0, [channel.id])],
            'allow_lead': True, 'allow_activity': True,
            'auto_continue': True, 'max_chain_steps': 2,
        })
        task = self.env['chatroom.ai.task'].create_from_channel(
            channel, task_type='qualify_lead', approval_required=False)
        task.action_plan()
        task.action_run()
        self.assertEqual(task.state, 'done')
        self.assertEqual(task.verification_state, 'verified')
        chained = self.env['chatroom.ai.task'].search([
            ('chain_parent_id', '=', task.id),
        ])
        self.assertTrue(chained)
        self.assertTrue(all(item.chain_step <= policy.max_chain_steps for item in chained))

    def test_task_verification_marks_missing_result_and_creates_exception(self):
        task = self.env['chatroom.ai.task'].create({
            'name': 'QA verificación de resultado',
            'task_type': 'qualify_lead',
            'state': 'done',
            'output_json': '[{"action":"create_lead","lead_id":99999999}]',
        })
        task._autonomy_verify_result()
        self.assertEqual(task.verification_state, 'warning')
        self.assertTrue(task.needs_human)
        self.assertTrue(self.env['chatroom.ai.autonomy.exception'].search_count([
            ('task_id', '=', task.id), ('exception_type', '=', 'verification'),
        ]))

    def test_task_verification_exposes_next_action_for_reply(self):
        task = self.env['chatroom.ai.task'].create({
            'name': 'QA siguiente acción',
            'task_type': 'prepare_reply',
            'state': 'done',
            'output_json': '[{"action":"prepare_reply","reply":"Hola, ¿en qué podemos ayudarte?"}]',
        })
        task._autonomy_verify_result()
        self.assertEqual(task.verification_state, 'verified')
        self.assertEqual(task.next_task_type, 'prepare_reply')
        self.assertIn('enviar', task.next_action.lower())

# -*- coding: utf-8 -*-
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestChatroomAiAgent(TransactionCase):

    def setUp(self):
        super().setUp()
        # Las pruebas del plan operativo deben ser deterministas y nunca
        # depender de una API externa configurada en la base de desarrollo.
        self.env['ir.config_parameter'].sudo().set_param(
            'chatroom_whatsapp.ai_enabled', 'False')
        self.env['ir.config_parameter'].sudo().set_param(
            'chatroom_ai_agent.event_orchestration', 'False')
        self.channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp',
            'external_id': 'ai-agent-test-001',
        })

    def test_task_generates_approved_plan_and_completes(self):
        task = self.env['chatroom.ai.task'].create_from_channel(
            self.channel, task_type='classify_customer',
            prompt='Clasifica este cliente para el siguiente seguimiento.',
        )
        task.action_plan()
        self.assertEqual(task.state, 'awaiting_approval')
        self.assertEqual(task.action_ids.mapped('key'), ['classify_customer'])
        task.action_approve()
        task.action_run()
        self.assertEqual(task.state, 'done')
        self.assertTrue(task.output_json)
        self.assertIn('Cliente clasificado', task.result_preview)
        self.assertTrue(task.audit_ids)

    def test_predefined_automations_are_visible_and_preview_safe(self):
        automations = self.env['chatroom.ai.automation'].with_context(
            active_test=False).search([])
        self.assertEqual(len(automations), 6)
        self.assertTrue(all(record.description for record in automations))
        self.assertTrue(all(record.instruction for record in automations))
        self.assertTrue(all(record.approval_required for record in automations))
        self.assertTrue(all(not record.active for record in automations))

        preview = automations[0].action_preview_scope()
        self.assertEqual(preview['type'], 'ir.actions.client')
        self.assertEqual(preview['tag'], 'display_notification')
        self.assertIn('No se creo ninguna tarea', preview['params']['message'])

    def test_completed_plan_exposes_human_result_in_channel_panel(self):
        task = self.env['chatroom.ai.task'].create_from_channel(
            self.channel, task_type='orchestrate',
            prompt='Revisa el contexto y prepara una respuesta.',
        )
        task.action_plan()
        task.action_approve()
        task.action_run()
        data = self.channel.get_ai_agent_data()
        self.assertEqual(data['task']['state'], 'done')
        self.assertIn('result_preview', data['task'])
        self.assertTrue(data['task']['result_preview'])

    def test_task_context_exposes_optional_knowledge_telemetry(self):
        task = self.env['chatroom.ai.task'].create_from_channel(
            self.channel, task_type='orchestrate',
            prompt='¿Qué productos y condiciones comerciales existen?',
        )
        context = task._context()
        if 'ai.knowledge.base' in self.env:
            self.assertIn('knowledge_context', context)
            self.assertIn('knowledge_sources', context)
            self.assertIn('knowledge_estimated_input_tokens', context)

    def test_task_persists_knowledge_sources_for_human_review(self):
        if 'ai.knowledge.base' not in self.env:
            self.skipTest('Base de conocimiento no instalada')
        manual = self.env['ai.knowledge.base'].create({
            'name': 'Fuente visible QA', 'source_type': 'text',
            'source_text': 'La tarifa de implementación es USD 20 por hora.',
        })
        manual.action_index()
        task = self.env['chatroom.ai.task'].create_from_channel(
            self.channel, task_type='prepare_reply', prompt='tarifa implementación')
        task.action_plan()
        self.assertIn('Fuente visible QA', task.knowledge_sources)
        self.assertGreaterEqual(task.knowledge_context_chars, 0)

    def test_memory_is_deduplicated(self):
        memory_model = self.env['chatroom.ai.memory']
        first = memory_model.remember('Cliente prefiere contacto por WhatsApp', channel=self.channel, memory_type='preference')
        second = memory_model.remember('Cliente prefiere contacto por WhatsApp', channel=self.channel, memory_type='preference')
        self.assertEqual(first, second)
        self.assertEqual(memory_model.search_count([('channel_id', '=', self.channel.id)]), 1)

    def test_simple_greeting_is_answered_locally_without_provider(self):
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('chatroom_whatsapp.ai_enabled', 'False')
        icp.set_param('chatroom_whatsapp.ai_require_approval', 'False')
        icp.set_param('chatroom_ai_agent.require_approval', 'False')
        self.env['chatroom.message'].create({
            'channel_id': self.channel.id, 'direction': 'inbound',
            'message_type': 'text', 'body': 'Hola',
        })
        with patch.object(type(self.channel), 'action_send_text', return_value=True):
            result = self.channel.action_ai_auto_reply_safe()
        self.assertEqual(result['status'], 'sent')
        suggestion = self.env['chatroom.ai.suggestion'].browse(result['suggestion_id'])
        self.assertEqual(suggestion.confidence, 1.0)
        self.assertIn('no consumió tokens', suggestion.safety_reason)

    def test_auto_reply_is_idempotent_after_latest_inbound(self):
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('chatroom_whatsapp.ai_enabled', 'False')
        self.env['chatroom.message'].create({
            'channel_id': self.channel.id, 'direction': 'inbound',
            'message_type': 'text', 'body': 'Consulta nueva',
        })
        self.env['chatroom.message'].with_context(chatroom_ai_generated=True).create({
            'channel_id': self.channel.id, 'direction': 'outbound',
            'message_type': 'text', 'body': 'Respuesta anterior',
        })
        result = self.channel.action_ai_auto_reply_safe()
        self.assertEqual(result['status'], 'already_replied')

    def test_sales_conversion_plan_is_approval_protected(self):
        task = self.env['chatroom.ai.task'].create_from_channel(
            self.channel, task_type='sales_conversion',
            prompt='Convierte esta conversación en una oportunidad y cotización.',
        )
        task.action_plan()
        self.assertEqual(task.state, 'awaiting_approval')
        self.assertEqual(
            task.action_ids.mapped('key'),
            ['search_catalog', 'classify_intent', 'create_lead', 'create_quotation', 'create_activity'],
        )
        self.assertFalse(task.action_ids.filtered(lambda action: action.key == 'search_catalog').requires_approval)
        self.assertTrue(all(task.action_ids.filtered(lambda action: action.key not in ('classify_intent', 'search_catalog')).mapped('requires_approval')))

    def test_automation_reports_execution_result(self):
        automation = self.env['chatroom.ai.automation'].create({
            'name': 'Prueba de seguimiento comercial',
            'trigger': 'open_opportunity',
            'task_type': 'followup',
            'approval_required': True,
            'max_tasks': 1,
        })
        notification = automation.action_run_now()
        self.assertEqual(notification.get('tag'), 'display_notification')
        self.assertGreaterEqual(automation.last_run_count, 0)
        self.assertTrue(automation.last_run)
        self.assertFalse(automation.last_error)

    def test_automation_propagates_retry_policy_to_tasks(self):
        automation = self.env['chatroom.ai.automation'].create({
            'name': 'Política de reintentos configurable',
            'trigger': 'open_conversation',
            'task_type': 'classify_customer',
            'approval_required': True,
            'max_tasks': 1,
            'max_attempts': 5,
        })
        task = self.env['chatroom.ai.task'].create_from_channel(
            self.channel, task_type=automation.task_type,
            prompt='Revisa el contexto del cliente.',
            approval_required=automation.approval_required,
            automation=automation,
        )
        self.assertEqual(task.max_attempts, 5)

    def test_ai_dashboard_actions_are_company_scoped(self):
        dashboard = self.env['chatroom.ai.dashboard'].create({})
        pending_action = dashboard.action_open_pending()
        self.assertIn(('company_id', '=', self.env.company.id), pending_action['domain'])
        self.assertEqual(dashboard.company_id, self.env.company)

    def test_playbook_examples_are_loaded_and_apply_to_current_chat(self):
        playbook_model = self.env['chatroom.ai.playbook']
        self.assertGreaterEqual(playbook_model.search_count([('is_example', '=', True)]), 9)
        playbook = playbook_model.search([('name', '=', 'Diagnóstico de conversación')], limit=1)
        self.assertTrue(playbook)
        data = self.channel.get_ai_agent_data()
        self.assertTrue(data['playbooks'])
        self.assertIn(playbook.id, [item['id'] for item in data['playbooks']])
        action = self.channel.action_ai_agent_apply_playbook(playbook.id)
        self.assertEqual(action['target'], 'new')
        task = self.env['chatroom.ai.task'].browse(action['res_id'])
        self.assertEqual(task.playbook_id, playbook)
        self.assertEqual(task.task_type, 'orchestrate')
        self.assertTrue(task.action_ids)

    def test_playbook_can_target_selected_partners_and_returns_task_list(self):
        partner = self.env['res.partner'].create({'name': 'Cliente acción guardada'})
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp',
            'external_id': 'ai-playbook-partner-001',
            'partner_id': partner.id,
        })
        playbook = self.env['chatroom.ai.playbook'].create({
            'name': 'Prueba cliente específico',
            'category': 'analysis',
            'task_type': 'classify_customer',
            'scope': 'partners',
            'partner_ids': [(6, 0, [partner.id])],
            'instruction': 'Clasifica este cliente y explica la prioridad.',
            'approval_required': True,
            'max_tasks': 5,
        })
        action = playbook.action_apply()
        self.assertEqual(action['res_model'], 'chatroom.ai.task')
        task = self.env['chatroom.ai.task'].search([
            ('playbook_id', '=', playbook.id), ('channel_id', '=', channel.id),
        ], limit=1)
        self.assertTrue(task)
        self.assertEqual(playbook.last_run_count, 1)

    def test_inbound_message_plans_task_for_active_automation(self):
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('chatroom_ai_agent.event_orchestration', 'True')
        icp.set_param('chatroom_ai_agent.enabled', 'True')
        icp.set_param('chatroom_ai_agent.mode', 'supervised')
        automation = self.env['chatroom.ai.automation'].create({
            'name': 'Orquestación al recibir consulta',
            'trigger': 'open_conversation',
            'task_type': 'classify_customer',
            'approval_required': True,
            'active': True,
        })
        self.env['chatroom.message'].create({
            'channel_id': self.channel.id, 'direction': 'inbound',
            'message_type': 'text', 'body': 'Necesito ayuda con mi cuenta',
        })
        task = self.env['chatroom.ai.task'].search([
            ('channel_id', '=', self.channel.id),
            ('automation_id', '=', automation.id),
        ], order='id desc', limit=1)
        self.assertTrue(task)
        self.assertEqual(task.state, 'awaiting_approval')
        self.assertEqual(task.action_ids.mapped('key'), ['classify_customer'])

    def test_inbound_message_executes_only_authorized_plan_in_automatic_mode(self):
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('chatroom_ai_agent.event_orchestration', 'True')
        icp.set_param('chatroom_ai_agent.enabled', 'True')
        icp.set_param('chatroom_ai_agent.mode', 'automatic')
        icp.set_param('chatroom_ai_agent.require_approval', 'False')
        automation = self.env['chatroom.ai.automation'].create({
            'name': 'Clasificación automática segura',
            'trigger': 'open_conversation',
            'task_type': 'classify_customer',
            'approval_required': False,
            'active': True,
        })
        self.env['chatroom.message'].create({
            'channel_id': self.channel.id, 'direction': 'inbound',
            'message_type': 'text', 'body': 'Quiero conocer mi categoría',
        })
        task = self.env['chatroom.ai.task'].search([
            ('channel_id', '=', self.channel.id),
            ('automation_id', '=', automation.id),
        ], order='id desc', limit=1)
        self.assertTrue(task)
        self.assertEqual(task.state, 'done')
        self.assertFalse(task.action_ids.filtered('requires_approval'))

    def test_commercial_automation_triggers_are_available(self):
        automation_model = self.env['chatroom.ai.automation']
        for trigger in ('open_opportunity', 'pending_quote', 'pending_activity'):
            automation = automation_model.create({
                'name': 'Prueba %s' % trigger,
                'trigger': trigger,
                'task_type': 'followup',
                'approval_required': True,
                'max_tasks': 1,
            })
            notification = automation.action_run_now()
            self.assertEqual(notification.get('tag'), 'display_notification')
            self.assertTrue(automation.last_run)

    def test_bulk_controls_keep_state_gates(self):
        planned = self.env['chatroom.ai.task'].create({
            'name': 'Tarea planificada de prueba', 'task_type': 'orchestrate', 'state': 'planned',
            'approval_required': False, 'channel_id': self.channel.id,
        })
        failed = self.env['chatroom.ai.task'].create({
            'name': 'Tarea fallida de prueba', 'task_type': 'orchestrate', 'state': 'failed',
            'approval_required': False, 'channel_id': self.channel.id,
        })
        run_notification = (planned | failed).action_run_selected()
        self.assertEqual(run_notification.get('tag'), 'display_notification')
        self.assertEqual(planned.state, 'done')
        retry_notification = (planned | failed).action_retry_selected()
        self.assertEqual(retry_notification.get('tag'), 'display_notification')
        self.assertEqual(failed.state, 'planned')

    def test_sales_actions_are_idempotent_on_retry(self):
        partner = self.env['res.partner'].create({
            'name': 'Cliente idempotencia IA',
            'phone': '+593999991111',
        })
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp',
            'external_id': 'ai-agent-idempotency-001',
            'partner_id': partner.id,
        })
        task = self.env['chatroom.ai.task'].create({
            'name': 'Prueba idempotencia comercial',
            'task_type': 'sales_conversion',
            'channel_id': channel.id,
            'company_id': channel.company_id.id,
            'approval_required': False,
        })
        lead_action = self.env['chatroom.ai.task.action'].create({
            'task_id': task.id, 'key': 'create_lead', 'name': 'Crear oportunidad',
            'requires_approval': False,
        })
        task._execute_action(lead_action)
        task._execute_action(lead_action)
        self.assertEqual(self.env['crm.lead'].search_count([
            ('partner_id', '=', partner.id), ('type', '=', 'opportunity'),
            ('company_id', '=', self.env.company.id),
        ]), 1)
        if 'sale.order' not in self.env:
            return
        quote_action = self.env['chatroom.ai.task.action'].create({
            'task_id': task.id, 'key': 'create_quotation', 'name': 'Crear cotización',
            'requires_approval': False,
        })
        task._execute_action(quote_action)
        task._execute_action(quote_action)
        self.assertEqual(self.env['sale.order'].search_count([
            ('partner_id', '=', partner.id), ('origin', '=', channel.display_name),
            ('company_id', '=', self.env.company.id),
        ]), 1)

    def test_cron_persists_failure_and_backoff(self):
        task = self.env['chatroom.ai.task'].create({
            'name': 'Tarea fallida en cron', 'task_type': 'orchestrate',
            'state': 'planned', 'approval_required': False,
            'channel_id': self.channel.id, 'next_run_at': fields.Datetime.now(),
        })
        with patch.object(type(task), 'action_run', side_effect=UserError('Fallo controlado')):
            self.env['chatroom.ai.task']._cron_run_pending()
        task.invalidate_recordset()
        self.assertEqual(task.state, 'failed')
        self.assertEqual(task.attempts, 1)
        self.assertIn('Fallo controlado', task.error_message)
        self.assertGreater(task.next_run_at, fields.Datetime.now())

    def test_agent_menu_is_exposed_from_chatroom_root(self):
        menu = self.env.ref('chatroom_ai_agent.menu_chatroom_ai_agent')
        self.assertEqual(menu.parent_id, self.env.ref('chatroom_whatsapp.menu_chatroom_root'))
        self.assertTrue(self.env.ref('chatroom_ai_agent.menu_chatroom_ai_tasks').action)
        self.assertTrue(self.env.ref('chatroom_ai_agent.menu_chatroom_ai_control').action)
        self.assertTrue(self.env.ref('chatroom_ai_agent.menu_chatroom_ai_approvals').action)
        self.assertTrue(self.env.ref('chatroom_ai_agent.menu_chatroom_ai_failed').action)

    def test_contact_panel_actions_are_dialog_safe(self):
        action_methods = {
            'action_view_leads': 'crm.lead',
            'action_view_sale_orders': 'sale.order',
            'action_view_purchases': 'purchase.order',
            'action_view_invoices': 'account.move',
            'action_view_tasks': 'project.task',
        }
        for method_name, model_name in action_methods.items():
            if model_name not in self.env:
                continue
            action = getattr(self.channel, method_name)()
            self.assertEqual(action.get('type'), 'ir.actions.act_window')
            self.assertEqual(action.get('target'), 'new')
            self.assertTrue(action.get('views'))
            self.assertIn((False, 'form'), action['views'])

    def test_setup_checklist_returns_a_clear_readiness_state(self):
        checklist = self.env['chatroom.ai.setup'].create({})
        checklist._refresh()
        self.assertIn(checklist.overall_state, ('ready', 'attention'))
        self.assertGreaterEqual(checklist.ready_count, 0)
        self.assertLessEqual(checklist.ready_count, checklist.total_checks)
        self.assertGreaterEqual(checklist.readiness_percent, 0)
        self.assertLessEqual(checklist.readiness_percent, 100)
        self.assertEqual(checklist.total_checks, 8)
        self.assertTrue(checklist.python_dependencies_ready)
        self.assertTrue(checklist.python_dependencies_detail)
        self.assertIn('OCR Python', checklist.ocr_detail)

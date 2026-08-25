# -*- coding: utf-8 -*-
from datetime import date

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestEngagementAutomation(TransactionCase):

    def test_render_message_replaces_known_and_unknown_tokens(self):
        execution = self.env['crm.engagement.execution']
        rendered = execution._render_message(
            'Hola ${first_name}; evento ${event_name}; ${missing}',
            {'first_name': 'Contacto 1', 'event_name': 'Reunión'},
        )
        self.assertEqual(rendered, 'Hola Contacto 1; evento Reunión; ')

    def test_step_rejects_unknown_variables(self):
        automation = self.env['crm.engagement.automation'].create({
            'name': 'Prueba de variables',
            'source_type': 'custom_event',
        })
        with self.assertRaises(ValidationError):
            self.env['crm.engagement.automation.step'].create({
                'automation_id': automation.id,
                'name': 'Variable invalida',
                'message_body': 'Hola ${variable_que_no_existe}',
            })

    def test_custom_event_candidate_is_deterministic(self):
        partner = self.env['res.partner'].create({
            'name': 'Contacto automatizacion',
            'email': 'automation@example.test',
        })
        event = self.env['crm.engagement.event'].create({
            'name': 'Renovación de prueba',
            'partner_id': partner.id,
            'event_date': date.today(),
            'event_type': 'other',
        })
        automation = self.env['crm.engagement.automation'].create({
            'name': 'Eventos de prueba',
            'source_type': 'custom_event',
        })
        step = self.env['crm.engagement.automation.step'].create({
            'automation_id': automation.id,
            'name': 'Aviso',
            'days_offset': 0,
            'message_body': 'Recordatorio ${event_name} para ${partner_name}',
        })
        candidates = automation._candidate_events(step, date.today())
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]['event_key'], 'event:%s' % event.id)

    def test_pending_execution_can_be_approved_and_executed(self):
        partner = self.env['res.partner'].create({'name': 'Contacto aprobacion'})
        automation = self.env['crm.engagement.automation'].create({
            'name': 'Aprobacion de prueba', 'source_type': 'custom_event',
        })
        step = self.env['crm.engagement.automation.step'].create({
            'automation_id': automation.id,
            'name': 'Aviso aprobado',
            'channel': 'notification',
            'requires_approval': True,
            'message_body': 'Hola ${first_name}',
        })
        execution = self.env['crm.engagement.execution'].create({
            'automation_id': automation.id,
            'step_id': step.id,
            'partner_id': partner.id,
            'event_key': 'approval:test',
            'event_name': 'Prueba',
            'scheduled_date': date.today(),
            'state': 'pending_approval',
            'context_json': '{"first_name": "Contacto"}',
        })
        manager_group = self.env.ref('crm_engagement_automation.group_crm_engagement_manager')
        manager = self.env['res.users'].create({
            'name': 'Administrador de pruebas',
            'login': 'engagement.manager.test',
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id, manager_group.id])],
        })
        result = execution.with_user(manager).action_approve()
        self.assertEqual(result['tag'], 'display_notification')
        self.assertEqual(execution.state, 'sent')

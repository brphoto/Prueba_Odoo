# -*- coding: utf-8 -*-
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestChatroomNotification(TransactionCase):

    def test_notification_inherits_channel_company(self):
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp', 'external_id': 'notification-company-test',
        })
        notification = self.env['chatroom.notification'].create({
            'name': 'Alerta de prueba', 'message': 'Revisar',
            'channel_id': channel.id,
        })
        self.assertEqual(notification.company_id, channel.company_id)

    def test_deduplication_and_lifecycle(self):
        model = self.env['chatroom.notification']
        vals = {
            'name': 'Prueba SLA', 'message': 'Atender conversación',
            'notification_type': 'sla', 'priority': '1',
            'dedupe_key': 'qa-notification-lifecycle',
        }
        first = model.create_deduplicated(vals)
        second = model.create_deduplicated(dict(vals, message='Mensaje actualizado'))
        self.assertEqual(first, second)
        self.assertEqual(first.message, 'Mensaje actualizado')
        first.action_mark_read()
        self.assertEqual(first.state, 'read')
        first.action_snooze()
        self.assertEqual(first.state, 'snoozed')
        first.action_reopen()
        first.action_resolve()
        self.assertEqual(first.state, 'done')

    def test_bulk_actions_return_visible_feedback(self):
        first = self.env['chatroom.notification'].create({
            'name': 'Aviso 1', 'message': 'Detalle 1', 'notification_type': 'other',
        })
        second = self.env['chatroom.notification'].create({
            'name': 'Aviso 2', 'message': 'Detalle 2', 'notification_type': 'other',
        })
        action = (first | second).action_resolve()
        self.assertEqual(action['tag'], 'display_notification')
        self.assertEqual((first | second).mapped('state'), ['done', 'done'])

    def test_done_dedupe_key_can_be_reused(self):
        model = self.env['chatroom.notification']
        vals = {
            'name': 'Alerta resuelta', 'message': 'Fin',
            'notification_type': 'other', 'dedupe_key': 'qa-notification-reuse',
        }
        first = model.create_deduplicated(vals)
        first.action_resolve()
        second = model.create_deduplicated(vals)
        self.assertNotEqual(first, second)

    def test_internal_delivery_is_explicit_and_traceable(self):
        notification = self.env['chatroom.notification'].create({
            'name': 'Aviso interno QA', 'message': 'Revisar conversación',
            'delivery_mode': 'internal',
        })
        action = notification.action_dispatch()
        self.assertEqual(notification.delivery_state, 'skipped')
        self.assertIn('solo para aviso interno', notification.delivery_error)
        self.assertEqual(action['tag'], 'display_notification')

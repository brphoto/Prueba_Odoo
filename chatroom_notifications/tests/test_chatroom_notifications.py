# -*- coding: utf-8 -*-
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestChatroomNotification(TransactionCase):

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

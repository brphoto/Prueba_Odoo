# -*- coding: utf-8 -*-
"""Pruebas de las reuniones desde una conversación.

El módulo no tenía ninguna. Se cubren la detección de solapes de agenda
(que es lo que evita citar a un agente a dos sitios a la vez) y los
contadores de reuniones, que en esta revisión se pasaron a consultas
agrupadas y conviene fijar que devuelven lo mismo.
"""
from datetime import datetime, timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestChatroomCalendar(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'QA calendario'})
        self.channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp',
            'external_id': '573001110001',
            'partner_id': self.partner.id,
            'assigned_user_id': self.env.user.id,
        })
        self.base = fields.Datetime.to_datetime('2026-10-05 15:00:00')

    def _event(self, start, hours=1, user=None, partners=None):
        return self.env['calendar.event'].create({
            'name': 'QA reunión',
            'start': start,
            'stop': start + timedelta(hours=hours),
            'user_id': (user or self.env.user).id,
            'partner_ids': [(6, 0, (partners or self.partner).ids)],
        })

    # ------------------------------------------------------------------
    # Solapes de agenda
    # ------------------------------------------------------------------

    def test_overlapping_meeting_is_detected(self):
        self._event(self.base)
        conflicts = self.channel._calendar_conflicts(
            self.base + timedelta(minutes=30), self.base + timedelta(minutes=90))
        self.assertTrue(conflicts, 'Un solape parcial debería detectarse.')

    def test_meeting_that_ends_exactly_when_the_other_starts_is_not_a_conflict(self):
        """Los límites son abiertos: encadenar reuniones es legítimo."""
        self._event(self.base, hours=1)
        conflicts = self.channel._calendar_conflicts(
            self.base + timedelta(hours=1), self.base + timedelta(hours=2))
        self.assertFalse(conflicts)

    def test_meeting_of_another_user_is_not_a_conflict(self):
        other = self.env['res.users'].create({
            'name': 'QA otro agente', 'login': 'qa_otro_agente_calendario',
        })
        self._event(self.base, user=other)
        self.assertFalse(
            self.channel._calendar_conflicts(
                self.base, self.base + timedelta(hours=1)),
            'La agenda de otro agente no bloquea la del asignado.')

    def test_conflicts_need_a_start_and_a_stop(self):
        self.assertFalse(self.channel._calendar_conflicts(False, self.base))
        self.assertFalse(self.channel._calendar_conflicts(self.base, False))

    # ------------------------------------------------------------------
    # Contadores de reuniones
    # ------------------------------------------------------------------

    def test_meeting_counters_match_the_partner_events(self):
        """El cálculo se pasó a consultas agrupadas: tiene que dar lo
        mismo que contar los eventos del contacto."""
        self._event(self.base)
        self._event(self.base + timedelta(days=1))
        self.channel.invalidate_recordset()
        self.assertEqual(self.channel.meeting_count, 2)

    def test_next_meeting_is_the_closest_one_still_ahead(self):
        past = fields.Datetime.now() - timedelta(days=2)
        soon = fields.Datetime.now() + timedelta(days=1)
        later = fields.Datetime.now() + timedelta(days=5)
        self._event(past)
        self._event(later)
        self._event(soon)
        self.channel.invalidate_recordset()
        self.assertEqual(
            fields.Datetime.to_string(self.channel.next_meeting_date)[:16],
            fields.Datetime.to_string(soon)[:16],
            'La próxima reunión debería ser la más cercana en el futuro.')

    def test_counters_are_empty_without_a_contact(self):
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp', 'external_id': '573001110002',
        })
        self.assertEqual(channel.meeting_count, 0)
        self.assertFalse(channel.next_meeting_date)

    def test_counters_ignore_events_of_other_contacts(self):
        other_partner = self.env['res.partner'].create({'name': 'QA ajeno'})
        self._event(self.base, partners=other_partner)
        self.channel.invalidate_recordset()
        self.assertEqual(self.channel.meeting_count, 0)

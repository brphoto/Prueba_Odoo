# -*- coding: utf-8 -*-
"""Pruebas de los enlaces de pago de Chatroom.

El módulo no tenía ninguna. Se cubre el ciclo de vida del enlace, que es
donde un fallo se paga caro: expirar un enlace ya cobrado, o dejar de
expirar la transacción asociada, deja al cliente pagando dos veces o al
comercio sin poder cobrar.
"""
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestChatroomPaymentLink(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'QA pagos'})
        self.channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp',
            'external_id': '573002220001',
            'partner_id': self.partner.id,
        })

    def _link(self, **values):
        return self.env['chatroom.payment.link'].create(dict({
            'name': 'QA enlace',
            'channel_id': self.channel.id,
            'partner_id': self.partner.id,
            'link': 'https://ejemplo.test/pagar/qa',
            'amount': 25.0,
            'currency_id': self.env.company.currency_id.id,
        }, **values))

    # ------------------------------------------------------------------
    # Mensaje de estado
    # ------------------------------------------------------------------

    def test_status_message_explains_every_state(self):
        """El mensaje es lo único que ve el agente en la conversación:
        cada estado tiene que decir algo distinto y accionable."""
        messages = {}
        for state in ('generated', 'sent', 'paid', 'expired', 'error'):
            link = self._link(state=state)
            messages[state] = link.status_message
            self.assertTrue(
                link.status_message,
                'El estado %s se quedó sin mensaje.' % state)
        self.assertEqual(
            len(set(messages.values())), len(messages),
            'Dos estados distintos no pueden dar el mismo mensaje.')

    def test_error_state_shows_the_provider_detail_when_there_is_one(self):
        link = self._link(state='error', error_message='Tarjeta rechazada')
        self.assertEqual(link.status_message, 'Tarjeta rechazada')

    def test_error_state_falls_back_to_a_generic_message(self):
        link = self._link(state='error')
        self.assertTrue(link.status_message)
        self.assertIn('proveedor', link.status_message.lower())

    # ------------------------------------------------------------------
    # Expiración
    # ------------------------------------------------------------------

    def test_a_paid_link_cannot_be_expired(self):
        """Expirar un cobro confirmado descuadraría la conciliación."""
        link = self._link(state='paid')
        with self.assertRaises(UserError):
            link.action_expire()
        self.assertEqual(link.state, 'paid')

    def test_expiring_a_pending_link_records_who_and_when(self):
        link = self._link(state='sent')
        link.action_expire()
        self.assertEqual(link.state, 'expired')
        self.assertTrue(link.synced_at)
        self.assertIn(
            self.env.user.display_name, link.error_message or '',
            'Debería quedar constancia de quién expiró el enlace.')

    def test_expiring_a_generated_link_is_allowed(self):
        link = self._link(state='generated')
        link.action_expire()
        self.assertEqual(link.state, 'expired')

    # ------------------------------------------------------------------
    # Sincronización
    # ------------------------------------------------------------------

    def test_sync_without_transactions_does_not_fail(self):
        """El cron corre aunque no haya nada que sincronizar."""
        self._link(state='sent')
        self.env['chatroom.payment.link']._cron_sync_transaction_states()

    def test_sync_now_returns_a_notification_for_the_agent(self):
        link = self._link(state='sent')
        action = link.action_sync_now()
        self.assertEqual(action['tag'], 'display_notification')
        self.assertTrue(action['params']['message'])

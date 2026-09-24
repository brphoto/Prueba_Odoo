# -*- coding: utf-8 -*-
"""Pruebas del conector de PayPhone.

El módulo no tenía ninguna. Se cubren las piezas que deciden cuánto se
cobra y qué transacción se marca como pagada, que es donde un fallo
cuesta dinero:

* la conversión de importes a centavos que se manda a PayPhone;
* la normalización del teléfono según el código de país;
* la lectura de la referencia y el id de transacción en la notificación,
  que llega con nombres de campo en cuatro grafías distintas;
* la validación de importe al confirmar, que es lo que impide dar por
  buena una notificación por un importe distinto al del pedido.
"""
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPaymentPayphone(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls.env.ref('payment_payphone.payment_provider_payphone')
        cls.provider.write({
            'state': 'test',
            'payphone_token': 'qa-token',
            'payphone_store_id': 'qa-store',
            'payphone_country_code': '593',
        })

    # ------------------------------------------------------------------
    # Importes
    # ------------------------------------------------------------------

    def test_amount_is_sent_to_payphone_in_cents(self):
        """PayPhone cobra en centavos: un error aquí es un error de precio."""
        self.assertEqual(self.provider._payphone_to_cents(1.0), 100)
        self.assertEqual(self.provider._payphone_to_cents(12.34), 1234)
        self.assertEqual(self.provider._payphone_to_cents(0.0), 0)

    def test_amount_rounds_instead_of_truncating(self):
        """0.1 + 0.2 en coma flotante es 0.30000000000000004: truncar
        cobraría 30 centavos en unos casos y 29 en otros."""
        self.assertEqual(self.provider._payphone_to_cents(0.1 + 0.2), 30)
        self.assertEqual(self.provider._payphone_to_cents(9.999), 1000)
        self.assertEqual(self.provider._payphone_to_cents(9.994), 999)

    # ------------------------------------------------------------------
    # Teléfono
    # ------------------------------------------------------------------

    def test_phone_with_country_code_becomes_local_format(self):
        self.assertEqual(
            self.provider._payphone_phone_number('593991234567'), '0991234567')

    def test_phone_already_local_is_left_alone(self):
        self.assertEqual(
            self.provider._payphone_phone_number('0991234567'), '0991234567')

    def test_phone_is_stripped_of_separators(self):
        self.assertEqual(
            self.provider._payphone_phone_number('+593 99 123 4567'), '0991234567')
        self.assertEqual(self.provider._payphone_phone_number(''), '')
        self.assertEqual(self.provider._payphone_phone_number(False), '')

    # ------------------------------------------------------------------
    # Lectura de la notificación
    # ------------------------------------------------------------------

    def test_reference_is_read_in_every_spelling_payphone_uses(self):
        """La notificación externa llega en PascalCase y la respuesta de
        la API en camelCase; ambas tienen que resolverse igual."""
        Transaction = self.env['payment.transaction']
        for payload in (
            {'clientTransactionId': 'REF-1'},
            {'clientTransactionID': 'REF-1'},
            {'ClientTransactionId': 'REF-1'},
            {'ClientTransactionID': 'REF-1'},
            {'reference': 'REF-1'},
            {'Reference': 'REF-1'},
        ):
            self.assertEqual(
                Transaction._payphone_notification_reference(payload), 'REF-1',
                'No se leyó la referencia en %s' % list(payload)[0])

    def test_missing_reference_is_reported_as_empty(self):
        self.assertFalse(
            self.env['payment.transaction']._payphone_notification_reference({}))

    def test_transaction_id_is_read_in_every_spelling(self):
        Transaction = self.env['payment.transaction']
        for payload in ({'id': 77}, {'transactionId': 77}, {'TransactionId': 77}):
            self.assertEqual(
                Transaction._payphone_notification_transaction_id(payload), '77')
        self.assertEqual(
            Transaction._payphone_notification_transaction_id({}), '')

    # ------------------------------------------------------------------
    # Contenido que se envía
    # ------------------------------------------------------------------

    def test_payload_carries_the_reference_and_the_store(self):
        transaction = self._transaction(amount=25.50)
        payload = self.provider._payphone_base_payload(transaction)
        self.assertEqual(payload['amount'], 2550)
        self.assertEqual(payload['reference'], transaction.reference)
        self.assertEqual(payload['clientTransactionId'], transaction.reference)
        self.assertEqual(payload['storeId'], 'qa-store')
        self.assertEqual(payload['currency'], transaction.currency_id.name)

    # ------------------------------------------------------------------
    # Confirmación
    # ------------------------------------------------------------------

    def test_a_response_with_a_different_amount_is_rejected(self):
        """La comprobación que impide dar por pagado un pedido cuando la
        pasarela responde por otro importe."""
        transaction = self._transaction(amount=10.0)
        transaction._payphone_update_from_response({
            'transactionId': '1', 'amount': 5000, 'statusCode': 3,
        })
        self.assertEqual(transaction.state, 'error')
        self.assertIn('amount', (transaction.state_message or '').lower())

    def test_a_response_with_the_right_amount_and_status_is_accepted(self):
        transaction = self._transaction(amount=10.0)
        transaction._payphone_update_from_response({
            'transactionId': '2', 'amount': 1000, 'statusCode': 3,
        })
        self.assertEqual(transaction.state, 'done')
        self.assertEqual(transaction.provider_reference, '2')

    def test_a_cancelled_response_cancels_the_transaction(self):
        transaction = self._transaction(amount=10.0)
        transaction._payphone_update_from_response({
            'transactionId': '3', 'amount': 1000, 'statusCode': 2,
            'message': 'Cancelado por el usuario',
        })
        self.assertEqual(transaction.state, 'cancel')

    def test_a_pending_response_leaves_the_transaction_pending(self):
        transaction = self._transaction(amount=10.0)
        transaction._payphone_update_from_response({
            'transactionId': '4', 'amount': 1000, 'statusCode': 1,
        })
        self.assertEqual(transaction.state, 'pending')

    # ------------------------------------------------------------------

    def _transaction(self, amount):
        partner = self.env['res.partner'].create({'name': 'QA PayPhone'})
        return self.env['payment.transaction'].create({
            'provider_id': self.provider.id,
            'payment_method_id': self.env.ref('payment.payment_method_card').id,
            'partner_id': partner.id,
            'amount': amount,
            'currency_id': self.env.ref('base.USD').id,
        })

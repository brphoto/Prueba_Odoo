from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPayPhone(TransactionCase):
    """Conector de cobro PayPhone.

    Son 800 líneas moviendo cobros y no tenían ningún test. Lo que se
    cubre aquí es lo que decide si un pago se da por bueno: la conversión
    a centavos, la lectura de la notificación (que llega en PascalCase o
    camelCase según el canal) y la validación del importe devuelto.
    """

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

    def test_amount_is_converted_to_cents_without_rounding_drift(self):
        """PayPhone cobra en centavos enteros.

        Un `int(amount * 100)` a secas se come un centavo en importes que
        en coma flotante quedan justo por debajo (19.99 -> 1998), y ese
        centavo es una diferencia de caja.
        """
        # Solo importes de dos decimales: son los unicos que existen en un
        # cobro real. Con medios centavos (1.005) el resultado depende de
        # como caiga el float y no tiene una respuesta "correcta" que
        # merezca fijarse en un test.
        casos = [(19.99, 1999), (0.01, 1), (100.0, 10000),
                 (0.0, 0), (1234.56, 123456), (0.99, 99)]
        for amount, esperado in casos:
            self.assertEqual(
                self.provider._payphone_to_cents(amount), esperado,
                'El importe %s deberia dar %s centavos.' % (amount, esperado))

    # ------------------------------------------------------------------
    # Telefono
    # ------------------------------------------------------------------

    def test_phone_number_drops_the_country_code(self):
        """PayPhone espera el numero local con cero inicial."""
        self.assertEqual(
            self.provider._payphone_phone_number('+593 99 123 4567'),
            '0991234567')
        self.assertEqual(
            self.provider._payphone_phone_number('0991234567'), '0991234567')
        self.assertEqual(self.provider._payphone_phone_number(''), '')
        self.assertEqual(self.provider._payphone_phone_number(False), '')

    # ------------------------------------------------------------------
    # Lectura de la notificacion
    # ------------------------------------------------------------------

    def test_reference_is_read_in_every_casing_paypone_uses(self):
        """El mismo dato llega con cuatro grafias segun el canal.

        La notificacion externa usa PascalCase y la respuesta de la API
        camelCase; si solo se mirara una, la mitad de los cobros no
        encontraria su transaccion en Odoo.
        """
        Transaction = self.env['payment.transaction']
        for clave in ('clientTransactionId', 'clientTransactionID',
                      'ClientTransactionId', 'ClientTransactionID',
                      'reference', 'Reference'):
            self.assertEqual(
                Transaction._payphone_notification_reference({clave: 'REF-001'}),
                'REF-001', 'No se leyo la referencia en la clave %s.' % clave)
        self.assertFalse(Transaction._payphone_notification_reference({}))

    def test_transaction_id_is_read_in_every_casing(self):
        Transaction = self.env['payment.transaction']
        for clave in ('id', 'transactionId', 'TransactionId'):
            self.assertEqual(
                Transaction._payphone_notification_transaction_id({clave: 12345}),
                '12345')
        self.assertEqual(
            Transaction._payphone_notification_transaction_id({}), '')

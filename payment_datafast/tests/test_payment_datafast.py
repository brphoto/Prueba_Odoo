from odoo.tests.common import TransactionCase


class TestPaymentDatafast(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls.env.ref('payment_datafast.payment_provider_datafast')
        cls.provider.write({
            'state': 'test',
            'datafast_entity_id': 'test-entity',
            'datafast_authorization': 'test-token',
            'datafast_merchant_id': '1000000406',
            'datafast_terminal_id': 'PD100406',
            'datafast_merchant_name': 'Odoo Test Commerce',
        })
        partner_values = {
            'name': 'John Customer',
            'email': 'john.customer@example.com',
            'vat': '1234567890',
            'phone': '0991234567',
            'street': 'Av. Test 123',
            'zip': '170000',
            'country_id': cls.env.ref('base.ec').id,
        }
        # Algunas instalaciones comerciales agregan una columna obligatoria
        # group_rfq a res.partner; otras no cargan ese módulo en el registro.
        # El fixture debe funcionar en ambos escenarios.
        if 'group_rfq' in cls.env['res.partner']._fields:
            partner_values['group_rfq'] = 'default'
        cls.partner = cls.env['res.partner'].create(partner_values)
        cls.currency = cls.env.ref('base.USD')
        cls.payment_method = cls.env.ref('payment.payment_method_card')

    def _create_transaction(self, **values):
        defaults = {
            'provider_id': self.provider.id,
            'payment_method_id': self.payment_method.id,
            'partner_id': self.partner.id,
            'amount': 10.0,
            'currency_id': self.currency.id,
            'reference': 'DATAFAST-TEST-001',
            'operation': 'online_direct',
        }
        defaults.update(values)
        return self.env['payment.transaction'].create(defaults)

    def test_checkout_payload_contains_phase_two_fields(self):
        tx = self._create_transaction()

        payload = tx._datafast_prepare_checkout_payload()

        self.assertEqual(payload['paymentType'], 'DB')
        self.assertEqual(payload['currency'], 'USD')
        self.assertEqual(payload['customer.identificationDocId'], '1234567890')
        self.assertEqual(payload['merchantTransactionId'], tx.reference)
        self.assertEqual(payload['testMode'], 'EXTERNAL')
        self.assertEqual(
            sum(float(payload[key]) for key in (
                'customParameters[SHOPPER_VAL_BASE0]',
                'customParameters[SHOPPER_VAL_BASEIMP]',
                'customParameters[SHOPPER_VAL_IVA]',
            )),
            10.0,
        )

    def test_optional_credit_configuration_is_sent(self):
        self.provider.write({
            'datafast_credit_type': '03',
            'datafast_installments': 6,
        })
        tx = self._create_transaction(reference='DATAFAST-TEST-OPTIONS')

        payload = tx._datafast_prepare_checkout_payload()

        self.assertEqual(payload['customParameters[SHOPPER_TIPOCREDITO]'], '03')
        self.assertEqual(payload['recurring.numberOfInstallments'], '6')

    def test_query_response_normalization_ignores_empty_entries(self):
        response = self.env['payment.transaction']._datafast_normalize_query_response({
            'payments': [{}, {'id': 'payment-1'}, {'id': 'payment-2'}],
        })

        self.assertEqual(response['id'], 'payment-2')

    def test_success_notification_marks_transaction_done(self):
        tx = self._create_transaction()

        tx._process('datafast', {
            'id': 'datafast-payment-001',
            'merchantTransactionId': tx.reference,
            'amount': '10.00',
            'currency': 'USD',
            'result': {'code': '000.100.112', 'description': 'Approved'},
        })

        self.assertEqual(tx.state, 'done')
        self.assertEqual(tx.provider_reference, 'datafast-payment-001')

    def test_registration_id_creates_payment_token(self):
        tx = self._create_transaction(tokenize=True)

        tx._process('datafast', {
            'id': 'datafast-payment-002',
            'merchantTransactionId': tx.reference,
            'registrationId': 'datafast-registration-002',
            'paymentBrand': 'VISA',
            'card': {'last4Digits': '1111'},
            'amount': '10.00',
            'currency': 'USD',
            'result': {'code': '000.100.112', 'description': 'Approved'},
        })

        self.assertEqual(tx.state, 'done')
        self.assertTrue(tx.token_id)
        self.assertEqual(tx.token_id.provider_ref, 'datafast-registration-002')

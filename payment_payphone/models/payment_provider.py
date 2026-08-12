import json
import logging
import pprint
import re

import requests
from werkzeug import urls

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.payment_payphone import const
from odoo.addons.payment_payphone.controllers.main import PayPhoneController

_logger = logging.getLogger(__name__)


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(
        selection_add=[('payphone', 'PayPhone')], ondelete={'payphone': 'set default'}
    )
    payphone_token = fields.Char(
        string='PayPhone Token', required_if_provider='payphone',
        groups='base.group_system',
    )
    payphone_store_id = fields.Char(
        string='PayPhone Store ID', required_if_provider='payphone',
    )
    payphone_country_code = fields.Char(
        string='Default country code', required_if_provider='payphone', default='593',
        help='E.164 country code used by API Sale. Ecuador is 593.',
    )
    payphone_flow = fields.Selection(
        selection=[
            ('sale', 'API Sale (PayPhone app)'),
            ('link', 'API Link (payment URL)'),
        ], string='PayPhone flow', default='sale', required=True,
    )

    def _compute_feature_support_fields(self):
        super()._compute_feature_support_fields()
        self.filtered(lambda p: p.code == 'payphone').update({
            'support_tokenization': False,
            'support_manual_capture': False,
            'support_refund': 'none',
            'support_express_checkout': False,
        })

    def _get_supported_currencies(self):
        supported = super()._get_supported_currencies()
        if self.code == 'payphone':
            supported = supported.filtered(lambda currency: currency.name in const.SUPPORTED_CURRENCIES)
        return supported

    def _get_default_payment_method_codes(self):
        default_codes = super()._get_default_payment_method_codes()
        if self.code != 'payphone':
            return default_codes
        return const.DEFAULT_PAYMENT_METHOD_CODES

    def _payphone_make_request(self, endpoint, method='GET', payload=None, reference=None):
        """Call PayPhone using the configured bearer token."""
        self.ensure_one()
        url = urls.url_join(const.API_BASE_URL + '/', endpoint.lstrip('/'))
        headers = {
            'Authorization': 'Bearer %s' % self.payphone_token,
            'Content-Type': 'application/json',
            'Accept-Language': 'es',
        }
        try:
            response = requests.request(
                method,
                url,
                headers=headers,
                json=payload if method.upper() != 'GET' else None,
                timeout=15,
            )
            response.raise_for_status()
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as error:
            _logger.exception('Could not reach PayPhone endpoint %s', url)
            raise ValidationError(_('PayPhone: could not establish the connection to PayPhone.')) from error
        except requests.exceptions.HTTPError as error:
            _logger.error(
                'PayPhone HTTP error at %s for transaction %s: %s',
                url, reference or self.id, response.text,
            )
            try:
                detail = response.json().get('message', response.text)
            except (ValueError, TypeError):
                detail = response.text
            raise ValidationError(_('PayPhone rejected the request: %s', detail)) from error

        try:
            return response.json()
        except (ValueError, json.JSONDecodeError):
            return response.text.strip()

    def _payphone_to_cents(self, amount):
        return int(round(amount * 100))

    def _payphone_phone_number(self, phone):
        value = re.sub(r'\D', '', phone or '')
        country_code = re.sub(r'\D', '', self.payphone_country_code or '')
        if value.startswith(country_code) and not value.startswith('0'):
            value = '0' + value[len(country_code):]
        return value

    def _payphone_base_payload(self, tx):
        amount = self._payphone_to_cents(tx.amount)
        return {
            'amount': amount,
            'amountWithoutTax': amount,
            'amountWithTax': 0,
            'tax': 0,
            'service': 0,
            'tip': 0,
            'currency': tx.currency_id.name,
            'reference': tx.reference,
            'clientTransactionId': tx.reference,
            'storeId': self.payphone_store_id,
        }

    def _payphone_create_sale(self, tx):
        phone = self._payphone_phone_number(tx.partner_phone)
        if not phone:
            raise ValidationError(_('PayPhone: the customer phone number is required for API Sale.'))
        payload = self._payphone_base_payload(tx)
        payload.update({
            'phoneNumber': phone,
            'countryCode': self.payphone_country_code,
            'responseUrl': urls.url_join(self.get_base_url(), PayPhoneController._response_url),
            'timeZone': -5,
        })
        return self._payphone_make_request('Sale', method='POST', payload=payload, reference=tx.reference)

    def _payphone_create_link(self, tx):
        payload = self._payphone_base_payload(tx)
        payload.update({
            'additionalData': tx.partner_name or tx.reference,
            'oneTime': True,
            'expireIn': 0,
            'isAmountEditable': False,
        })
        response = self._payphone_make_request('Links', method='POST', payload=payload, reference=tx.reference)
        if isinstance(response, str) and response.startswith(('http://', 'https://')):
            return response
        if isinstance(response, dict):
            link = response.get('link') or response.get('url') or response.get('paymentUrl')
            if link:
                return link
        _logger.error('Unexpected PayPhone Link response: %s', pprint.pformat(response))
        raise ValidationError(_('PayPhone did not return a valid payment link.'))

    def _payphone_get_sale_status(self, transaction_id=None, client_transaction_id=None):
        if transaction_id:
            return self._payphone_make_request('Sale/%s' % transaction_id, method='GET')
        return self._payphone_make_request(
            'Sale/client/%s' % client_transaction_id, method='GET',
        )

    def _payphone_check_user(self, phone, country_code=None):
        country_code = country_code or self.payphone_country_code
        phone = self._payphone_phone_number(phone)
        return self._payphone_make_request(
            'Users/check/%s/region/%s' % (phone, country_code), method='GET',
        )

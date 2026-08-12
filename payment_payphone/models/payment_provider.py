import json
import logging
import pprint
import re
from urllib.parse import urlencode

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
            ('box', 'Cajita de Pagos (inline Web)'),
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
        return {
            'payphone_link' if self.payphone_flow == 'link'
            else 'payphone_box' if self.payphone_flow == 'box'
            else 'payphone_sale'
        }

    def _get_redirect_form_view(self, is_validation=False):
        """Always return this module's redirect form for PayPhone."""
        self.ensure_one()
        if self.code == 'payphone' and self.payphone_flow != 'box':
            return self.env.ref('payment_payphone.redirect_form')
        return super()._get_redirect_form_view(is_validation=is_validation)

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

    def _payphone_confirm_box(self, transaction_id, client_transaction_id, reference=None):
        """Confirm a Cajita payment immediately after PayPhone redirects back."""
        self.ensure_one()
        if not transaction_id or not client_transaction_id:
            raise ValidationError(_('PayPhone: the Cajita response is missing its transaction identifiers.'))
        url = urls.url_join(const.BOX_API_BASE_URL + '/', 'confirm')
        try:
            response = requests.post(
                url,
                headers={
                    'Authorization': 'Bearer %s' % self.payphone_token,
                    'Content-Type': 'application/json',
                    'Accept-Language': 'es',
                },
                json={'id': int(transaction_id), 'clientTxId': client_transaction_id},
                timeout=15,
            )
            response.raise_for_status()
            return response.json()
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as error:
            _logger.exception('Could not confirm PayPhone Cajita transaction %s.', reference or self.id)
            raise ValidationError(_('PayPhone: could not confirm the Cajita payment.')) from error
        except requests.exceptions.HTTPError as error:
            _logger.error('PayPhone Cajita confirmation error for %s: %s', reference or self.id, response.text)
            try:
                detail = response.json().get('message', response.text)
            except (ValueError, TypeError):
                detail = response.text
            raise ValidationError(_('PayPhone rejected the Cajita confirmation: %s', detail)) from error
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            raise ValidationError(_('PayPhone returned an invalid Cajita confirmation.')) from error

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
            'responseUrl': '%s?%s' % (
                urls.url_join(self.get_base_url(), PayPhoneController._response_url),
                urlencode({'reference': tx.reference}),
            ),
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

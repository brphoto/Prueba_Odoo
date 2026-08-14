import base64
import hashlib
import logging
import random
from datetime import datetime, timedelta, timezone

import requests

from odoo import _, fields, models
from odoo.exceptions import ValidationError
from odoo.http import request as http_request
from odoo.tools.urls import urljoin

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment_placetopay import const

_logger = logging.getLogger(__name__)


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(
        selection_add=[('placetopay', "PlacetoPay")], ondelete={'placetopay': 'set default'}
    )
    placetopay_login = fields.Char(
        string="PlacetoPay Login",
        required_if_provider='placetopay',
        copy=False,
    )
    placetopay_secret_key = fields.Char(
        string="PlacetoPay Secret Key",
        required_if_provider='placetopay',
        copy=False,
        groups='base.group_system',
    )
    placetopay_base_url = fields.Char(
        string="PlacetoPay Base URL",
        required_if_provider='placetopay',
        default=const.DEFAULT_BASE_URL,
        copy=False,
        help="Host assigned by PlacetoPay for your account, without a trailing slash. Use "
             "https://checkout-test.placetopay.com for sandbox testing. Production hosts are "
             "region-specific (e.g. https://checkout-co.placetopay.com for Colombia or "
             "https://checkout.placetopay.ec for Ecuador); use the one provided by PlacetoPay.",
    )
    placetopay_locale = fields.Selection(
        selection=const.LOCALE_SELECTION,
        string="Checkout Language",
        default='es_CO',
        required_if_provider='placetopay',
    )
    placetopay_document_type = fields.Selection(
        selection=const.DOCUMENT_TYPE_SELECTION,
        string="Default Document Type",
        default='CC',
        required_if_provider='placetopay',
        help="Used as the payer's document type when no more specific value can be derived from "
             "the customer's record.",
    )

    # === COMPUTE METHODS === #

    def _compute_feature_support_fields(self):
        """Override of `payment` to enable additional features."""
        super()._compute_feature_support_fields()
        self.filtered(lambda p: p.code == 'placetopay').update({
            'support_tokenization': False,
            'support_express_checkout': False,
            'support_refund': 'none',
            'support_manual_capture': None,
        })

    # === BUSINESS METHODS === #

    def _get_default_payment_method_codes(self):
        """Override of `payment` to return the default payment method codes."""
        self.ensure_one()
        if self.code != 'placetopay':
            return super()._get_default_payment_method_codes()
        return const.DEFAULT_PAYMENT_METHOD_CODES

    def _placetopay_get_base_url(self):
        self.ensure_one()
        return (self.placetopay_base_url or const.DEFAULT_BASE_URL).rstrip('/')

    def _placetopay_build_auth(self):
        """Build the `auth` object required by every PlacetoPay API call.

        See https://docs.placetopay.dev/checkout/authentication: tranKey is
        Base64(SHA-256(nonce + seed + secretKey)) where nonce is a random,
        single-use value and seed is an ISO-8601 timestamp no older than 5
        minutes when the request reaches PlacetoPay.
        """
        self.ensure_one()
        if not self.placetopay_login or not self.placetopay_secret_key:
            raise ValidationError(_("PlacetoPay: the Login and Secret Key must be configured."))

        seed = datetime.now(timezone.utc).astimezone().isoformat()
        raw_nonce = str(random.SystemRandom().randint(10 ** 9, 10 ** 10 - 1))
        tran_key = base64.b64encode(
            hashlib.sha256((raw_nonce + seed + self.placetopay_secret_key).encode()).digest()
        ).decode()
        nonce = base64.b64encode(raw_nonce.encode()).decode()
        return {
            'login': self.placetopay_login,
            'tranKey': tran_key,
            'nonce': nonce,
            'seed': seed,
        }

    def _placetopay_make_request(self, endpoint, payload):
        """Call the PlacetoPay REST API and return the decoded JSON body."""
        self.ensure_one()
        url = urljoin(self._placetopay_get_base_url() + '/', endpoint.lstrip('/'))
        try:
            response = requests.post(
                url, json=payload, headers={'Content-Type': 'application/json'}, timeout=30,
            )
            response.raise_for_status()
        except requests.exceptions.ConnectionError:
            _logger.exception("Could not reach PlacetoPay endpoint %s", url)
            raise ValidationError(_("PlacetoPay: could not establish the connection to PlacetoPay."))
        except requests.exceptions.HTTPError:
            _logger.exception("PlacetoPay HTTP error at %s: %s", url, response.text)
            raise ValidationError(_("PlacetoPay rejected the request. Please check your credentials."))

        try:
            return response.json()
        except ValueError:
            raise ValidationError(_("PlacetoPay returned an invalid response."))

    def _placetopay_create_session(self, payload):
        self.ensure_one()
        data = self._placetopay_make_request(const.SESSION_ENDPOINT, payload)
        status = (data.get('status') or {}).get('status')
        if status != 'OK' or not data.get('processUrl') or not data.get('requestId'):
            message = (data.get('status') or {}).get('message') or _("Unknown error.")
            raise ValidationError(_("PlacetoPay did not accept the session request: %s", message))
        return data

    def _placetopay_query_session(self, request_id):
        self.ensure_one()
        endpoint = f'{const.SESSION_ENDPOINT}/{request_id}'
        payload = {'auth': self._placetopay_build_auth()}
        return self._placetopay_make_request(endpoint, payload)

    def _placetopay_get_ip_address(self):
        if http_request:
            return payment_utils.get_customer_ip_address()
        return '127.0.0.1'

    def _placetopay_get_user_agent(self):
        if http_request and http_request.httprequest:
            return http_request.httprequest.user_agent.string or 'Odoo'
        return 'Odoo'

    @staticmethod
    def _placetopay_expiration():
        return (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()

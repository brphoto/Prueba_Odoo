import json
import logging
from urllib.parse import urlsplit

import requests

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


_logger = logging.getLogger(__name__)


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(
        selection_add=[('datafast', 'Datafast')],
        ondelete={'datafast': 'set default'},
    )
    datafast_entity_id = fields.Char(
        string='Entity ID',
        required_if_provider='datafast',
        copy=False,
    )
    datafast_authorization = fields.Char(
        string='Authorization Bearer Token',
        required_if_provider='datafast',
        copy=False,
        groups='base.group_system',
    )
    datafast_merchant_id = fields.Char(
        string='Merchant ID (MID)',
        required_if_provider='datafast',
        copy=False,
    )
    datafast_terminal_id = fields.Char(
        string='Terminal ID (TID)',
        required_if_provider='datafast',
        copy=False,
    )
    datafast_merchant_name = fields.Char(
        string='Merchant Name for Risk Checks',
        required_if_provider='datafast',
        copy=False,
    )
    datafast_api_url = fields.Char(
        string='Gateway URL',
        default='https://test.oppwa.com',
        required_if_provider='datafast',
        copy=False,
        help='Use https://eu-test.oppwa.com for testing and the production URL supplied by Datafast in production.',
    )
    datafast_brands = fields.Char(
        string='Card Brands',
        default='VISA MASTER DINERS DISCOVER AMEX',
        required_if_provider='datafast',
        copy=False,
    )
    datafast_credit_type = fields.Char(
        string='Credit Type Code',
        copy=False,
        help=(
            'Optional Datafast code for the credit mode, e.g. 00 for current, '
            '01/02/03 for diferidos, or 07 for diferido with grace months.'
        ),
    )
    datafast_installments = fields.Integer(
        string='Installments',
        copy=False,
        help='Optional number of installments sent to Datafast. Leave at 0 for current payment.',
    )

    @api.constrains('datafast_installments')
    def _check_datafast_installments(self):
        for provider in self.filtered(lambda provider: provider.code == 'datafast'):
            if provider.datafast_installments < 0 or provider.datafast_installments > 99:
                raise ValidationError(_('Datafast installments must be between 0 and 99.'))

    @api.depends('code')
    def _compute_view_configuration_fields(self):
        super()._compute_view_configuration_fields()
        self.filtered(lambda provider: provider.code == 'datafast').update({
            'show_allow_tokenization': True,
            'show_allow_express_checkout': False,
        })

    @api.depends('code')
    def _compute_feature_support_fields(self):
        super()._compute_feature_support_fields()
        self.filtered(lambda provider: provider.code == 'datafast').update({
            'support_tokenization': True,
            'support_manual_capture': None,
            'support_express_checkout': False,
            'support_refund': 'partial',
        })

    def _get_default_payment_method_codes(self):
        self.ensure_one()
        if self.code != 'datafast':
            return super()._get_default_payment_method_codes()
        return {'datafast'}

    def _datafast_make_request(self, endpoint, method='GET', payload=None):
        self.ensure_one()
        if not self.datafast_api_url or not self.datafast_entity_id or not self.datafast_authorization:
            raise ValidationError(_('Datafast credentials are not fully configured.'))

        base_url = self.datafast_api_url.strip().rstrip('/')
        parsed_base_url = urlsplit(base_url)
        if parsed_base_url.scheme != 'https' or not parsed_base_url.netloc:
            raise ValidationError(_('The Datafast gateway URL must be a valid HTTPS URL.'))

        endpoint = endpoint.strip()
        if not endpoint or '..' in endpoint or endpoint.startswith('http://') or endpoint.startswith('https://'):
            raise ValidationError(_('The Datafast endpoint is invalid.'))
        url = f'{base_url}/{endpoint.lstrip("/")}'
        method = method.upper()
        headers = {
            'Authorization': f'Bearer {self.datafast_authorization}',
            'Accept': 'application/json',
        }
        try:
            request_kwargs = {'headers': headers, 'timeout': 30}
            request_kwargs['params' if method in ('GET', 'DELETE') else 'data'] = payload
            response = requests.request(method, url, **request_kwargs)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as error:
            _logger.exception('Datafast API request failed at %s', url)
            raise ValidationError(_('Could not communicate with Datafast: %s', error)) from error
        except (ValueError, json.JSONDecodeError) as error:
            raise ValidationError(_('Datafast returned an invalid response.')) from error

import logging
import pprint
from urllib.parse import quote as url_quote

from odoo import _, api, models
from odoo.tools.urls import urljoin

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment_placetopay import const
from odoo.addons.payment_placetopay.controllers.main import PlaceToPayController

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    # === BUSINESS METHODS === #

    @api.model
    def _cron_check_pending_placetopay_transactions(self):
        """Query pending PlacetoPay sessions in the background.

        PlacetoPay's Checkout API does not push server-to-server notifications,
        so transactions whose browser never returned to Odoo (closed tab,
        network issue) are re-checked here to avoid staying stuck as pending.
        """
        transactions = self.search([
            ('provider_code', '=', 'placetopay'),
            ('state', 'in', ('draft', 'pending')),
            ('provider_reference', '!=', False),
        ], order='id asc', limit=20)
        for tx in transactions:
            try:
                tx._placetopay_query_and_process()
            except Exception:
                _logger.exception("Unable to query PlacetoPay transaction %s.", tx.reference)

    def _get_specific_rendering_values(self, processing_values):
        """Override of `payment` to return PlacetoPay-specific rendering values."""
        if self.provider_code != 'placetopay':
            return super()._get_specific_rendering_values(processing_values)

        payload = self._placetopay_prepare_session_payload()
        session_data = self.provider_id._placetopay_create_session(payload)

        self.provider_reference = str(session_data['requestId'])
        self._set_pending()

        return {'api_url': session_data['processUrl']}

    def _placetopay_prepare_session_payload(self):
        """Build the payload sent to POST /api/session.

        See https://docs.placetopay.dev/checkout/api/reference/session.
        """
        self.ensure_one()
        provider = self.provider_id
        partner = self.partner_id
        base_url = provider.get_base_url()
        return_url = '%s?%s' % (
            urljoin(base_url, PlaceToPayController._return_url),
            'ref=' + url_quote(self.reference),
        )
        first_name, last_name = payment_utils.split_partner_name(self.partner_name or '')

        person = {
            'document': (partner.vat or '').strip(),
            'documentType': provider.placetopay_document_type,
            'name': first_name or self.partner_name or '',
            'surname': last_name or '',
            'email': self.partner_email or '',
            'mobile': self.partner_phone or '',
            'address': {
                'street': self.partner_address or '',
                'city': self.partner_city or '',
                'country': partner.country_id.code or '',
            },
        }

        return {
            'auth': provider._placetopay_build_auth(),
            'locale': provider.placetopay_locale or 'es_CO',
            'payer': person,
            'buyer': person,
            'payment': {
                'reference': self.reference,
                'description': f"{provider.company_id.name or 'Odoo'} - {self.reference}"[:255],
                'amount': {
                    'currency': self.currency_id.name,
                    'total': self._placetopay_convert_amount(),
                },
                'allowPartial': False,
            },
            'expiration': provider._placetopay_expiration(),
            'returnUrl': return_url,
            'cancelUrl': return_url,
            'ipAddress': provider._placetopay_get_ip_address(),
            'userAgent': provider._placetopay_get_user_agent(),
        }

    def _placetopay_convert_amount(self):
        """Round the transaction amount to the currency's minor unit."""
        return round(self.amount, self.currency_id.decimal_places)

    def _placetopay_query_and_process(self):
        """Query the current session status at PlacetoPay and apply it to `self`."""
        self.ensure_one()
        if not self.provider_reference:
            return
        response = self.provider_id._placetopay_query_session(self.provider_reference)
        _logger.info(
            "PlacetoPay session status for transaction %s:\n%s",
            self.reference, pprint.pformat(response),
        )
        payment_data = dict(response, reference=self.reference)
        self.env['payment.transaction'].sudo()._process('placetopay', payment_data)

    @staticmethod
    def _placetopay_get_last_payment(payment_data):
        payments = payment_data.get('payment') or []
        return payments[-1] if payments else {}

    @api.model
    def _extract_reference(self, provider_code, payment_data):
        """Override of `payment` to extract the reference from the payment data."""
        if provider_code != 'placetopay':
            return super()._extract_reference(provider_code, payment_data)
        return payment_data.get('reference')

    def _extract_amount_data(self, payment_data):
        """Override of `payment` to extract the amount and currency from the payment data."""
        if self.provider_code != 'placetopay':
            return super()._extract_amount_data(payment_data)

        last_payment = self._placetopay_get_last_payment(payment_data)
        amount_data = last_payment.get('amount')
        if not amount_data:
            # No payment attempt has completed yet: fall back to the amount that was
            # requested when the session was created.
            amount_data = ((payment_data.get('request') or {}).get('payment') or {}).get('amount') or {}
        total = amount_data.get('total')
        if total is None:
            return None
        return {
            'amount': float(total),
            'currency_code': amount_data.get('currency'),
        }

    def _apply_updates(self, payment_data):
        """Override of `payment` to update the transaction based on the payment data."""
        if self.provider_code != 'placetopay':
            return super()._apply_updates(payment_data)

        last_payment = self._placetopay_get_last_payment(payment_data)
        status_block = last_payment.get('status') or payment_data.get('status') or {}
        status = (status_block.get('status') or '').upper()
        provider_message = status_block.get('message') or ''

        if last_payment.get('internalReference'):
            self.provider_reference = str(last_payment['internalReference'])

        if status in const.STATUS_MAPPING['done']:
            details = ', '.join(filter(None, [
                last_payment.get('authorization') and _("Authorization: %s", last_payment['authorization']),
                last_payment.get('receipt') and _("Receipt: %s", last_payment['receipt']),
            ])) or provider_message
            self._set_done(details)
        elif status in const.STATUS_MAPPING['canceled']:
            self._set_canceled(provider_message or _("The customer canceled the payment."))
        elif status in const.STATUS_MAPPING['pending'] or not status:
            self._set_pending(provider_message or None)
        elif status in const.STATUS_MAPPING['error']:
            self._set_error(provider_message or _("PlacetoPay rejected the payment."))
        else:
            _logger.warning(
                "Received data for transaction %s with unknown PlacetoPay status: %s.",
                self.reference, status,
            )
            self._set_error(provider_message or _("Received data with invalid status: %s.", status))

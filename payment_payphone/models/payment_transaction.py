import logging

from werkzeug import urls

from odoo import _, api, models
from odoo.exceptions import ValidationError

from odoo.addons.payment_payphone.controllers.main import PayPhoneController

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    @api.model
    def _cron_check_pending_payphone_transactions(self):
        """Query pending API Sale transactions in the background.

        PayPhone allows querying API Sale by transactionId. API Link is not
        included here because PayPhone documents that it has no system return;
        API Link is finalized through the external notification webhook.
        Keep the batch below PayPhone's documented 30 GET/minute limit.
        """
        transactions = self.search([
            ('provider_code', '=', 'payphone'),
            ('state', 'in', ('draft', 'pending', 'error')),
            ('provider_reference', '!=', False),
        ], order='id asc', limit=20)
        for tx in transactions:
            try:
                tx._payphone_query_status()
            except Exception:
                _logger.exception('Unable to query PayPhone transaction %s.', tx.reference)

    def _get_specific_rendering_values(self, processing_values):
        values = super()._get_specific_rendering_values(processing_values)
        if self.provider_code != 'payphone':
            return values

        if self.provider_id.payphone_flow == 'link':
            api_url = self.provider_id._payphone_create_link(self)
            self._set_pending()
            # API Link has no browser callback. Keep the Odoo reference in the
            # redirect form so the checkout tab can poll the transaction.
            return {'api_url': api_url, 'reference': self.reference}

        if self.provider_reference and self.state in ('pending', 'done'):
            wait_url = urls.url_join(self.provider_id.get_base_url(), PayPhoneController._wait_url)
            return {'api_url': wait_url, 'reference': self.reference}

        response = self.provider_id._payphone_create_sale(self)
        if not isinstance(response, dict):
            raise ValidationError(_('PayPhone returned an invalid API Sale response.'))
        # API Sale initially returns only transactionId. The final status is
        # obtained by a later GET request.
        if response.get('transactionId') and not (
            response.get('statusCode') or response.get('transactionStatus')
        ):
            self.provider_reference = str(response['transactionId'])
            self._set_pending()
        else:
            self._payphone_update_from_response(response)
        wait_url = urls.url_join(self.provider_id.get_base_url(), PayPhoneController._wait_url)
        return {'api_url': wait_url, 'reference': self.reference}

    def _get_specific_processing_values(self, processing_values):
        values = super()._get_specific_processing_values(processing_values)
        if self.provider_code == 'payphone' and self.provider_id.payphone_flow == 'box':
            self._set_pending()
            values.update({
                'payphone_box': True,
                'payphone_box_token': self.provider_id.payphone_token,
                'payphone_box_store_id': self.provider_id.payphone_store_id,
                'payphone_box_amount': self.provider_id._payphone_to_cents(self.amount),
                'payphone_box_reference': self.reference,
                'payphone_box_currency': self.currency_id.name,
            })
        return values

    def _payphone_notification_reference(self, notification_data):
        """Return the Odoo reference sent back by PayPhone."""
        return (
            notification_data.get('clientTransactionId')
            or notification_data.get('clientTransactionID')
            or notification_data.get('ClientTransactionId')
            or notification_data.get('ClientTransactionID')
            or notification_data.get('reference')
            or notification_data.get('Reference')
        )

    def _payphone_notification_transaction_id(self, notification_data):
        return str(
            notification_data.get('id')
            or notification_data.get('transactionId')
            or notification_data.get('TransactionId')
            or ''
        )

    # Odoo 19 notification API.
    @api.model
    def _extract_reference(self, provider_code, payment_data):
        if provider_code != 'payphone':
            return super()._extract_reference(provider_code, payment_data)
        return self._payphone_notification_reference(payment_data)

    def _extract_amount_data(self, payment_data):
        if self.provider_code == 'payphone':
            # The responseUrl only contains id and clientTransactionId. The
            # amount is obtained from PayPhone's confirm endpoint below.
            return None
        return super()._extract_amount_data(payment_data)

    def _apply_updates(self, payment_data):
        if self.provider_code != 'payphone':
            return super()._apply_updates(payment_data)

        transaction_id = self._payphone_notification_transaction_id(payment_data)
        client_transaction_id = self._payphone_notification_reference(payment_data) or self.reference
        if self.provider_id.payphone_flow == 'box':
            response = self.provider_id._payphone_confirm_box(
                transaction_id, client_transaction_id, reference=self.reference,
            )
        else:
            response = self.provider_id._payphone_get_sale_status(
                transaction_id=transaction_id or None,
                client_transaction_id=client_transaction_id if not transaction_id else None,
            )
        if not isinstance(response, dict):
            raise ValidationError(_('PayPhone returned an invalid transaction status.'))
        self._payphone_update_from_response(response)

    def _payphone_query_status(self):
        """Query a PayPhone transaction without manufacturing a notification."""
        self.ensure_one()
        if self.provider_id.payphone_flow in ('link', 'box') and not self.provider_reference:
            return
        response = self.provider_id._payphone_get_sale_status(
            transaction_id=self.provider_reference or None,
            client_transaction_id=None if self.provider_reference else self.reference,
        )
        if not isinstance(response, dict):
            raise ValidationError(_('PayPhone returned an invalid transaction status.'))
        self._payphone_update_from_response(response)

    def _payphone_update_from_response(self, response):
        # External notifications use PascalCase while API responses use camelCase.
        response = {
            (key[:1].lower() + key[1:] if key else key): value
            for key, value in response.items()
        }
        transaction_id = response.get('transactionId') or response.get('id')
        if transaction_id:
            self.provider_reference = str(transaction_id)

        expected_amount = self.provider_id._payphone_to_cents(self.amount)
        received_amount = response.get('amount')
        if received_amount is not None and int(received_amount) != expected_amount:
            self._set_error(_('PayPhone: the returned amount does not match the Odoo transaction.'))
            return

        status_code = response.get('statusCode')
        status = str(response.get('transactionStatus') or '').lower()
        if str(status_code) == '3' or status in ('approved', 'approved '):
            self._set_done()
        elif str(status_code) == '2' or status in ('canceled', 'cancelled', 'rejected'):
            self._set_canceled(response.get('message') or _('PayPhone canceled the transaction.'))
        elif str(status_code) == '1' or status in ('pending', ''):
            self._set_pending()
        else:
            message = response.get('message') or _('Unknown PayPhone transaction status.')
            self._set_error(message)

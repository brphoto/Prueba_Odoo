import logging

from werkzeug import urls

from odoo import _, models
from odoo.exceptions import ValidationError

from odoo.addons.payment_payphone.controllers.main import PayPhoneController

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

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

    def _get_tx_from_notification_data(self, provider_code, notification_data):
        tx = super()._get_tx_from_notification_data(provider_code, notification_data)
        if provider_code != 'payphone' or len(tx) == 1:
            return tx

        client_reference = (
            notification_data.get('clientTransactionId')
            or notification_data.get('clientTransactionID')
            or notification_data.get('ClientTransactionId')
            or notification_data.get('ClientTransactionID')
            or notification_data.get('reference')
            or notification_data.get('Reference')
        )
        transaction_id = str(
            notification_data.get('id')
            or notification_data.get('transactionId')
            or notification_data.get('TransactionId')
            or ''
        )
        if client_reference:
            tx = self.search([
                ('reference', '=', client_reference),
                ('provider_code', '=', 'payphone'),
            ], limit=1)
        elif transaction_id:
            tx = self.search([
                ('provider_reference', '=', transaction_id),
                ('provider_code', '=', 'payphone'),
            ], limit=1)
        if not tx:
            raise ValidationError(_('PayPhone: no transaction matches the notification.'))
        return tx

    def _process_notification_data(self, notification_data):
        super()._process_notification_data(notification_data)
        if self.provider_code != 'payphone':
            return

        transaction_id = str(
            notification_data.get('id')
            or notification_data.get('transactionId')
            or notification_data.get('TransactionId')
            or ''
        )
        client_transaction_id = (
            notification_data.get('clientTransactionId')
            or notification_data.get('clientTransactionID')
            or notification_data.get('ClientTransactionId')
            or notification_data.get('ClientTransactionID')
            or self.reference
        )
        response = self.provider_id._payphone_get_sale_status(
            transaction_id=transaction_id or None,
            client_transaction_id=client_transaction_id if not transaction_id else None,
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

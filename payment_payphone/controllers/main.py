import logging

from odoo import http
from odoo.exceptions import ValidationError
from odoo.http import request
from odoo.addons.payment.controllers.post_processing import PaymentPostProcessing

_logger = logging.getLogger(__name__)


class PayPhoneController(http.Controller):
    _response_url = '/payment/payphone/response'
    _notification_url = '/payment/payphone/NotificacionPago'
    _wait_url = '/payment/payphone/wait'
    _status_url = '/payment/payphone/status'

    @http.route(_response_url, type='http', auth='public', methods=['GET', 'POST'], csrf=False)
    def payphone_response(self, **data):
        """Receive PayPhone's responseUrl notification and verify it server-side."""
        _logger.info('PayPhone notification received: %s', data)
        try:
            request.env['payment.transaction'].sudo()._handle_notification_data('payphone', data)
        except ValidationError:
            # Acknowledge the notification while logging invalid data. The transaction is never
            # marked as paid from the callback alone; it is queried from PayPhone first.
            _logger.exception('Unable to process PayPhone notification.')
        return request.make_json_response({'ok': True})

    @http.route([_notification_url, '/payment/payphone/notification'], type='http', auth='public', methods=['POST'], csrf=False)
    def payphone_external_notification(self, **kwargs):
        """Receive PayPhone's approved-payment notification for API Link."""
        try:
            data = request.get_json_data() or {}
        except Exception:
            data = request.httprequest.get_json(silent=True) or {}
        _logger.info('PayPhone external notification received: %s', data)
        try:
            request.env['payment.transaction'].sudo()._handle_notification_data('payphone', data)
        except ValidationError:
            _logger.exception('Unable to process PayPhone external notification.')
            return request.make_json_response({'Response': False, 'ErrorCode': '222'})
        return request.make_json_response({'Response': True, 'ErrorCode': '000'})

    @http.route(_wait_url, type='http', auth='public', methods=['GET'])
    def payphone_wait(self, reference=None, **kwargs):
        tx = request.env['payment.transaction'].sudo().search([
            ('reference', '=', reference),
            ('provider_code', '=', 'payphone'),
        ], limit=1)
        if not tx:
            return request.redirect('/payment/status')
        PaymentPostProcessing.monitor_transaction(tx)
        return request.render('payment_payphone.wait', {'tx': tx})

    @http.route(_status_url, type='http', auth='public', methods=['GET'])
    def payphone_status(self, reference=None, **kwargs):
        tx = request.env['payment.transaction'].sudo().search([
            ('reference', '=', reference),
            ('provider_code', '=', 'payphone'),
        ], limit=1)
        if tx:
            PaymentPostProcessing.monitor_transaction(tx)
        # Also retry an old error transaction when it already has PayPhone's
        # transaction id. Earlier module versions could mark the initial
        # transactionId-only response as an error.
        if tx and (tx.state in ('draft', 'pending') or (
            tx.state == 'error' and tx.provider_reference
        )):
            try:
                notification_data = {'clientTransactionId': reference}
                if tx.provider_reference:
                    notification_data['id'] = tx.provider_reference
                tx._handle_notification_data('payphone', notification_data)
            except Exception:
                _logger.exception('Unable to poll PayPhone transaction status.')
                tx.invalidate_recordset()
        return request.make_json_response({'state': tx.state if tx else 'error'})

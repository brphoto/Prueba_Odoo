import logging

from odoo import http
from odoo.exceptions import ValidationError
from odoo.http import request

_logger = logging.getLogger(__name__)


class PayPhoneController(http.Controller):
    _response_url = '/payment/payphone/response'
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

    @http.route(_wait_url, type='http', auth='public', methods=['GET'])
    def payphone_wait(self, reference=None, **kwargs):
        tx = request.env['payment.transaction'].sudo().search([
            ('reference', '=', reference),
            ('provider_code', '=', 'payphone'),
        ], limit=1)
        if not tx:
            return request.redirect('/payment/status')
        return request.render('payment_payphone.wait', {'tx': tx})

    @http.route(_status_url, type='http', auth='public', methods=['GET'])
    def payphone_status(self, reference=None, **kwargs):
        tx = request.env['payment.transaction'].sudo().search([
            ('reference', '=', reference),
            ('provider_code', '=', 'payphone'),
        ], limit=1)
        return request.make_json_response({'state': tx.state if tx else 'error'})

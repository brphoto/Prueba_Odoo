import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class PlaceToPayController(http.Controller):
    _return_url = '/payment/placetopay/return'

    @http.route(_return_url, type='http', auth='public', methods=['GET'], csrf=False)
    def placetopay_return_from_checkout(self, **data):
        """Handle the browser redirection back from PlacetoPay's hosted checkout.

        PlacetoPay does not offer a server-to-server webhook for the Checkout
        product, so the Odoo reference is embedded in the `returnUrl` we sent
        when creating the session, and the final status is fetched right here
        by querying the session (also retried by a background cron as a
        safety net in case the browser redirect never happens).
        """
        reference = data.get('ref')
        _logger.info("Handling PlacetoPay return for reference %s with data:\n%s", reference, data)
        tx_sudo = request.env['payment.transaction'].sudo().search([
            ('reference', '=', reference),
            ('provider_code', '=', 'placetopay'),
        ], limit=1)
        if tx_sudo:
            try:
                tx_sudo._placetopay_query_and_process()
            except Exception:
                _logger.exception("Unable to query the PlacetoPay session for reference %s.", reference)
        else:
            _logger.warning("No PlacetoPay transaction found for reference %s.", reference)

        return request.redirect('/payment/status')

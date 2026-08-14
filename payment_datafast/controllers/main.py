import logging
from urllib.parse import urlsplit

from odoo import http
from odoo.addons.payment import utils as payment_utils
from odoo.http import request


_logger = logging.getLogger(__name__)


class DatafastController(http.Controller):
    _return_url = '/payment/datafast/return'

    @http.route(
        _return_url,
        type='http',
        auth='public',
        methods=['GET'],
        csrf=False,
        save_session=False,
    )
    def datafast_return_from_checkout(self, **data):
        resource_path = data.get('resourcePath', '')
        parsed_resource_path = urlsplit(resource_path)
        resource_path = parsed_resource_path.path
        if (
            not resource_path.startswith('/v1/')
            or '..' in resource_path
            or parsed_resource_path.netloc
            or parsed_resource_path.query
        ):
            _logger.warning('Datafast returned an invalid resourcePath.')
            return request.redirect('/payment/status')

        transactions = request.env['payment.transaction'].sudo()
        provider_id = data.get('provider_id', '')
        provider = request.env['payment.provider'].sudo().browse(
            int(provider_id)
        ).exists() if provider_id.isdigit() else request.env['payment.provider']
        if provider.code != 'datafast' or provider.state not in ['test', 'enabled']:
            provider = request.env['payment.provider']
        if not provider:
            _logger.error('No active Datafast provider was found while processing a return.')
            return request.redirect('/payment/status')

        try:
            tx = request.env['payment.transaction']
            tx_id = data.get('tx_id', '')
            access_token = data.get('access_token')
            if tx_id.isdigit():
                tx = transactions.browse(int(tx_id)).exists()
                if (
                    not tx
                    or tx.provider_id != provider
                    or not payment_utils.check_access_token(
                        access_token, tx.partner_id.id, tx.amount, tx.currency_id.id
                    )
                ):
                    _logger.warning('Datafast return failed transaction access validation.')
                    return request.redirect('/payment/status')

            response = provider._datafast_make_request(
                resource_path,
                method='GET',
                payload={'entityId': provider.datafast_entity_id},
            )
            if tx:
                tx._process('datafast', response)
            else:
                transactions._process('datafast', response)
        except Exception:
            _logger.exception('Could not process the Datafast return.')

        return request.redirect('/payment/status')

import logging
from urllib.parse import quote

from odoo import models


_logger = logging.getLogger(__name__)


class PaymentToken(models.Model):
    _inherit = 'payment.token'

    def _handle_archiving(self):
        """Delete the registration at Datafast before archiving it in Odoo."""
        datafast_tokens = self.filtered(
            lambda token: token.provider_code == 'datafast' and token.provider_ref
        )
        for token in datafast_tokens:
            endpoint = f'v1/registrations/{quote(token.provider_ref, safe="")}'
            token.provider_id._datafast_make_request(
                endpoint,
                method='DELETE',
                payload={'entityId': token.provider_id.datafast_entity_id},
            )
            _logger.info(
                'Deleted Datafast registration %s for Odoo token %s.',
                token.provider_ref,
                token.id,
            )
        return super()._handle_archiving()

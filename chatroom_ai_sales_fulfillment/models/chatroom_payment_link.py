# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models


class ChatroomPaymentLink(models.Model):
    _inherit = 'chatroom.payment.link'

    ai_sales_retry_attempts = fields.Integer(string='Reintentos automáticos', default=0, copy=False)
    ai_sales_last_retry_at = fields.Datetime(string='Último reintento automático', copy=False)

    @api.model
    def _fulfillment_int_param(self, key, default):
        env = self.env
        value = env['ir.config_parameter'].sudo().get_param(key, str(default))
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return default

    @api.model
    def _cron_sync_transaction_states(self):
        env = self.env
        result = super()._cron_sync_transaction_states()
        icp = env['ir.config_parameter'].sudo()
        if icp.get_param('chatroom_ai_sales.payment_retry_enabled') != 'True':
            return result
        hours = max(1, self._fulfillment_int_param('chatroom_ai_sales.payment_retry_hours', 24))
        maximum = max(1, self._fulfillment_int_param('chatroom_ai_sales.payment_retry_max', 1))
        cutoff = fields.Datetime.now() - timedelta(hours=hours)
        links = self.sudo().search([
            ('state', '=', 'error'),
            ('ai_sales_retry_attempts', '<', maximum),
            ('create_date', '<=', cutoff),
        ], limit=100)
        for link in links:
            try:
                link.action_resend()
                link.write({
                    'ai_sales_retry_attempts': link.ai_sales_retry_attempts + 1,
                    'ai_sales_last_retry_at': fields.Datetime.now(),
                })
                channel = link.channel_id
                if channel and hasattr(channel, '_sales_log'):
                    channel._sales_log('payment_retry', 'Se reenvió automáticamente un enlace de pago fallido.', amount=link.amount)
            except Exception as exc:  # noqa: BLE001 - el cron debe continuar con los demás enlaces
                link.write({'ai_sales_retry_attempts': link.ai_sales_retry_attempts + 1, 'ai_sales_last_retry_at': fields.Datetime.now()})
                link.error_message = str(exc)
        return result

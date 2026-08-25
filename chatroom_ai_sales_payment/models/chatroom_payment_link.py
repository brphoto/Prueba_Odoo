# -*- coding: utf-8 -*-
import logging

from odoo import _, fields, models


_logger = logging.getLogger(__name__)


class ChatroomPaymentLink(models.Model):
    _inherit = 'chatroom.payment.link'

    ai_sales_postprocessed = fields.Boolean(string='Postventa procesada', default=False, copy=False, index=True)
    ai_sales_payment_notified = fields.Boolean(string='Pago notificado', default=False, copy=False)
    ai_sales_invoice_id = fields.Many2one('account.move', string='Factura postventa', copy=False)
    ai_sales_postprocess_attempts = fields.Integer(string='Intentos postventa', default=0, copy=False)
    ai_sales_postprocess_error = fields.Text(string='Error postventa', copy=False)
    ai_sales_payment_event_logged = fields.Boolean(string='Evento de pago registrado', default=False, copy=False)

    def _ai_sales_invoice_for_order(self, order):
        invoices = order.invoice_ids.filtered(
            lambda invoice: invoice.move_type == 'out_invoice' and invoice.state != 'cancel')
        return invoices[:1]

    def _ai_sales_process_paid_link(self, link):
        link.ensure_one()
        channel = link.channel_id.sudo()
        order = self.env['sale.order'].sudo().browse(link.res_id).exists() \
            if link.res_model == 'sale.order' else self.env['sale.order'].browse()
        if channel:
            channel.write({'ai_sales_status': 'payment_received'})
            if not link.ai_sales_payment_event_logged:
                channel._sales_log(
                    'payment_received',
                    _('El proveedor confirmó el pago del enlace %s.') % link.display_name,
                    order=order,
                    amount=link.amount,
                )
                link.ai_sales_payment_event_logged = True

        icp = self.env['ir.config_parameter'].sudo()
        if (
            order
            and icp.get_param('chatroom_ai_sales.auto_create_invoice', 'False') == 'True'
            and not link.ai_sales_invoice_id
        ):
            invoice = self._ai_sales_invoice_for_order(order)
            if not invoice:
                if order.state != 'sale':
                    raise ValueError(_('El pedido todavía no está confirmado para generar la factura.'))
                invoice = order._create_invoices()[:1]
            if invoice:
                link.ai_sales_invoice_id = invoice.id
                channel._sales_log(
                    'invoice_created',
                    _('Factura preparada: %s.') % invoice.display_name,
                    order=order,
                    amount=invoice.amount_total,
                )
                if (
                    icp.get_param('chatroom_ai_sales.auto_post_invoice', 'False') == 'True'
                    and invoice.state == 'draft'
                ):
                    invoice.action_post()

        if (
            channel
            and icp.get_param('chatroom_ai_sales.notify_payment', 'True') == 'True'
            and not link.ai_sales_payment_notified
        ):
            message = _('Pago recibido correctamente.')
            if order:
                message += ' ' + _('Tu pedido %s está confirmado.') % order.name
            if link.ai_sales_invoice_id:
                message += ' ' + _('La factura %s fue preparada.') % link.ai_sales_invoice_id.display_name
            if not channel._sales_send_text(message):
                raise ValueError(_('No se pudo notificar el pago por WhatsApp.'))
            link.ai_sales_payment_notified = True
            channel._sales_log('post_sale_notified', _('Se notificó el pago al cliente.'), order=order)
            channel.write({'ai_sales_status': 'post_sale'})

        link.write({
            'ai_sales_postprocessed': True,
            'ai_sales_postprocess_error': False,
        })

    def _cron_sync_transaction_states(self):
        result = super()._cron_sync_transaction_states()
        if self.env['ir.config_parameter'].sudo().get_param(
                'chatroom_ai_sales.enabled', 'False') != 'True':
            return result
        links = self.sudo().search([
            ('state', '=', 'paid'),
            ('ai_sales_postprocessed', '=', False),
        ], order='id')
        for link in links:
            try:
                with self.env.cr.savepoint():
                    link._ai_sales_process_paid_link(link)
            except Exception as exc:  # noqa: BLE001 - el cron debe continuar con los demás pagos
                link.sudo().write({
                    'ai_sales_postprocess_attempts': link.ai_sales_postprocess_attempts + 1,
                    'ai_sales_postprocess_error': str(exc)[:4000],
                })
                _logger.warning(
                    'Postventa pendiente para el enlace de pago %s (intento %s): %s',
                    link.id, link.ai_sales_postprocess_attempts, exc,
                )
        return result

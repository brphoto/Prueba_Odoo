from uuid import uuid4

from odoo import _, models
from odoo.exceptions import ValidationError


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    def _chatroom_create_payment_link(self, related_document):
        """Create a PayPhone API Link for a document sent from Chatroom."""
        self.ensure_one()
        self = self.sudo()
        related_document = related_document.sudo()
        if self.code != 'payphone' or self.payphone_flow != 'link':
            raise ValidationError(_('El proveedor PayPhone no está configurado para API Link.'))
        if not hasattr(related_document, '_get_default_payment_link_values'):
            raise ValidationError(_(
                'Este tipo de documento no soporta generar un link de pago.'))

        payment_values = related_document._get_default_payment_link_values()
        amount = payment_values.get('amount')
        partner = self.env['res.partner'].browse(payment_values.get('partner_id')).exists()
        currency = self.env['res.currency'].browse(payment_values.get('currency_id')).exists()
        if not amount or amount <= 0:
            raise ValidationError(_('No hay un valor pendiente positivo para este documento.'))
        if not partner:
            raise ValidationError(_('El documento no tiene un cliente para el link de PayPhone.'))
        if not currency:
            raise ValidationError(_('El documento no tiene moneda para el link de PayPhone.'))

        payment_method = self.with_context(active_test=False).payment_method_ids.filtered(
            lambda method: method.active and method.code == 'payphone_link'
        )[:1]
        if not payment_method:
            raise ValidationError(_(
                'El método de pago PayPhone Link no está activo. Actívalo en el proveedor.'))

        transaction_values = {
            'provider_id': self.id,
            'payment_method_id': payment_method.id,
            'reference': 'CHAT-%s-%s-%s' % (
                related_document._name.replace('.', '-').upper(),
                related_document.id,
                uuid4().hex[:10],
            ),
            'amount': amount,
            'currency_id': currency.id,
            'partner_id': partner.id,
            'operation': 'online_redirect',
            'landing_route': '/payment/confirmation',
        }
        transaction_model = self.env['payment.transaction']
        if related_document._name == 'sale.order' and 'sale_order_ids' in transaction_model._fields:
            transaction_values['sale_order_ids'] = [(6, 0, [related_document.id])]
        elif related_document._name == 'account.move' and 'invoice_ids' in transaction_model._fields:
            transaction_values['invoice_ids'] = [(6, 0, [related_document.id])]

        transaction = transaction_model.sudo().create(transaction_values)
        transaction._log_sent_message()
        payment_link = self._payphone_create_link(transaction)
        transaction._set_pending()
        return payment_link

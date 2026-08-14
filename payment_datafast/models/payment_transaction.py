import logging
from datetime import timedelta

from werkzeug.urls import url_encode

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.urls import urljoin as url_join

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment_datafast.controllers.main import DatafastController


_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    def _get_specific_processing_values(self, processing_values):
        values = super()._get_specific_processing_values(processing_values)
        if self.provider_code != 'datafast' or self.operation in ('online_token', 'offline'):
            return values

        payload = self._datafast_prepare_checkout_payload()
        response = self.provider_id._datafast_make_request(
            'v1/checkouts', method='POST', payload=payload
        )
        checkout_id = response.get('id')
        result = response.get('result') or {}
        if not checkout_id:
            raise ValidationError(_(
                'Datafast did not return a checkout ID: %s',
                result.get('description') or result.get('code') or _('Unknown error'),
            ))

        self.provider_reference = checkout_id
        access_token = payment_utils.generate_access_token(
            self.partner_id.id, self.amount, self.currency_id.id
        )
        return {
            'datafast_checkout_id': checkout_id,
            'datafast_widget_url': (
                f'{self.provider_id.datafast_api_url.rstrip("/")}/v1/paymentWidgets.js'
            ),
            'datafast_shopper_result_url': url_join(
                self.provider_id.get_base_url(),
                f'{DatafastController._return_url}?{url_encode({
                    "provider_id": self.provider_id.id,
                    "tx_id": self.id,
                    "access_token": access_token,
                })}',
            ),
            'datafast_brands': self.provider_id.datafast_brands,
            'datafast_tokenization_enabled': self.tokenize,
        }

    def _datafast_prepare_checkout_payload(self):
        self.ensure_one()
        if self.currency_id.name != 'USD':
            raise ValidationError(_('Datafast only supports USD transactions.'))

        name_parts = (self.partner_name or '').split()
        if len(name_parts) < 2 or len(name_parts[0]) < 3 or len(name_parts[-1]) < 3:
            raise ValidationError(_(
                'Datafast requires the customer first name and surname with at least 3 characters.'
            ))
        if not self.partner_email or len(self.partner_email) < 6:
            raise ValidationError(_('Datafast requires a valid customer email.'))
        if not self.partner_id.vat:
            raise ValidationError(_('Datafast requires the customer identification number.'))
        if not self.partner_phone or len(self.partner_phone) < 7:
            raise ValidationError(_('Datafast requires a valid customer phone number.'))
        if not self.partner_address:
            raise ValidationError(_('Datafast requires the customer billing address.'))

        first_name = name_parts[0]
        last_name = name_parts[-1]
        middle_name = ' '.join(name_parts[1:-1])
        country_code = self.partner_country_id.code or 'EC'
        base_zero, taxable_base, tax_amount = self._datafast_tax_values()
        payload = {
            'entityId': self.provider_id.datafast_entity_id,
            'amount': f'{self.amount:.2f}',
            'currency': 'USD',
            'paymentType': 'DB',
            'customer.givenName': first_name,
            'customer.surname': last_name,
            'customer.ip': payment_utils.get_customer_ip_address(),
            'customer.merchantCustomerId': str(self.partner_id.id)[:16],
            'merchantTransactionId': self.reference,
            'customer.email': self.partner_email,
            'customer.identificationDocType': 'IDCARD',
            'customer.identificationDocId': self._datafast_identification_id(),
            'customer.phone': self.partner_phone,
            'billing.street1': self.partner_address,
            'billing.country': country_code,
            'billing.postcode': self.partner_zip or '',
            'shipping.street1': self.partner_address,
            'shipping.country': country_code,
            'customParameters[SHOPPER_MID]': self.provider_id.datafast_merchant_id,
            'customParameters[SHOPPER_TID]': self.provider_id.datafast_terminal_id,
            'customParameters[SHOPPER_ECI]': '0103910',
            'customParameters[SHOPPER_PSERV]': '17913101',
            'customParameters[SHOPPER_VAL_BASE0]': f'{base_zero:.2f}',
            'customParameters[SHOPPER_VAL_BASEIMP]': f'{taxable_base:.2f}',
            'customParameters[SHOPPER_VAL_IVA]': f'{tax_amount:.2f}',
            'risk.parameters[USER_DATA2]': self.provider_id.datafast_merchant_name,
            'customParameters[SHOPPER_VERSIONDF]': '2',
        }
        if middle_name:
            payload['customer.middleName'] = middle_name
        if self.provider_id.state == 'test':
            payload['testMode'] = 'EXTERNAL'
        if self.provider_id.datafast_credit_type:
            payload['customParameters[SHOPPER_TIPOCREDITO]'] = (
                self.provider_id.datafast_credit_type.strip()
            )
        if self.provider_id.datafast_installments:
            payload['recurring.numberOfInstallments'] = str(
                self.provider_id.datafast_installments
            )

        lines = self._datafast_order_lines()
        if not lines:
            payload.update({
                'cart.items[0].name': 'Pago Odoo',
                'cart.items[0].description': self.reference,
                'cart.items[0].price': f'{self.amount:.2f}',
                'cart.items[0].quantity': '1',
            })
            return payload

        for index, line in enumerate(lines):
            payload.update({
                f'cart.items[{index}].name': (
                    line.product_id.display_name or 'Producto'
                )[:255].replace('&', 'y'),
                f'cart.items[{index}].description': (
                    line.name or line.product_id.display_name or 'Producto'
                )[:255].replace('&', 'y'),
                f'cart.items[{index}].price': f'{line.price_unit:.2f}',
                f'cart.items[{index}].quantity': f'{line.product_uom_qty:.3f}',
            })
        return payload

    def _datafast_identification_id(self):
        value = ''.join(character for character in (self.partner_id.vat or '') if character.isalnum())
        return value[-10:].zfill(10)

    def _datafast_order_lines(self):
        self.ensure_one()
        if 'sale.order.line' not in self.env.registry.models:
            return []
        if 'sale_order_ids' in self._fields and self.sale_order_ids:
            return self.sale_order_ids[:1].order_line.filtered(lambda line: not line.display_type)
        return self.env['sale.order.line']

    def _datafast_tax_values(self):
        self.ensure_one()
        lines = self._datafast_order_lines()
        invoice_lines = self._datafast_invoice_lines() if not lines else []
        if not lines and not invoice_lines:
            return self.amount, 0.0, 0.0

        base_zero = 0.0
        taxable_base = 0.0
        tax_amount = 0.0
        tax_lines = lines or invoice_lines
        for line in tax_lines:
            line_base = line.price_subtotal
            tax_amount = 0.0
            taxes = line.tax_id if hasattr(line, 'tax_id') else line.tax_ids
            if taxes:
                tax_values = taxes.compute_all(
                    line.price_unit,
                    currency=self.currency_id,
                    quantity=(
                        line.product_uom_qty
                        if hasattr(line, 'product_uom_qty') else line.quantity
                    ),
                    product=line.product_id,
                    partner=self.partner_id,
                )
                tax_amount = sum(tax.get('amount', 0.0) for tax in tax_values.get('taxes', []))
            if tax_amount:
                taxable_base += line_base
            else:
                base_zero += line_base

        if lines:
            tax_amount = self.sale_order_ids[:1].amount_tax if (
                'sale_order_ids' in self._fields and self.sale_order_ids
            ) else 0.0
        else:
            tax_amount = sum(invoice.amount_tax for invoice in self.invoice_ids)
        base_zero += self.amount - (base_zero + taxable_base + tax_amount)
        return max(base_zero, 0.0), max(taxable_base, 0.0), max(tax_amount, 0.0)

    def _datafast_invoice_lines(self):
        self.ensure_one()
        if 'invoice_ids' not in self._fields or not self.invoice_ids:
            return []
        return self.invoice_ids.invoice_line_ids.filtered(
            lambda line: not line.display_type
        )

    def _datafast_prepare_token_payment_payload(self):
        self.ensure_one()
        if not self.token_id or self.token_id.provider_code != 'datafast':
            raise UserError(_('The Datafast transaction is not linked to a valid payment token.'))
        payload = self._datafast_prepare_checkout_payload()
        payload['registrations[0].id'] = self.token_id.provider_ref
        return payload

    def _send_payment_request(self):
        if self.provider_code != 'datafast':
            return super()._send_payment_request()
        response = self.provider_id._datafast_make_request(
            'v1/payments', method='POST', payload=self._datafast_prepare_token_payment_payload()
        )
        self._process('datafast', response)

    def _send_refund_request(self):
        if self.provider_code != 'datafast':
            return super()._send_refund_request()
        source_transaction = self.source_transaction_id
        if not source_transaction.provider_reference:
            raise ValidationError(_('The original Datafast payment has no provider reference.'))
        payload = {
            'entityId': self.provider_id.datafast_entity_id,
            'amount': f'{-self.amount:.2f}',
            'currency': 'USD',
            'paymentType': 'RF',
            'merchantTransactionId': self.reference,
        }
        if self.provider_id.state == 'test':
            payload['testMode'] = 'EXTERNAL'
        response = self.provider_id._datafast_make_request(
            f'v1/payments/{source_transaction.provider_reference}',
            method='POST',
            payload=payload,
        )
        response.setdefault('merchantTransactionId', self.reference)
        self._process('datafast', response)

    def _datafast_verify(self):
        self.ensure_one()
        if self.provider_code != 'datafast':
            return self
        response = self.provider_id._datafast_make_request(
            'v1/query',
            method='GET',
            payload={
                'entityId': self.provider_id.datafast_entity_id,
                'merchantTransactionId': self.reference,
            },
        )
        response = self._datafast_normalize_query_response(response)
        if not response:
            return self
        response.setdefault('merchantTransactionId', self.reference)
        self._process('datafast', response)
        return self

    @staticmethod
    def _datafast_normalize_query_response(response):
        if isinstance(response, list):
            candidates = response
        elif isinstance(response, dict) and isinstance(response.get('payments'), list):
            candidates = response['payments']
        elif isinstance(response, dict):
            candidates = [response]
        else:
            candidates = []
        candidates = [candidate for candidate in candidates if candidate.get('id')]
        return candidates[-1] if candidates else {}

    @api.model
    def _cron_datafast_verify_pending(self):
        cutoff = fields.Datetime.now() - timedelta(minutes=2)
        transactions = self.search([
            ('provider_code', '=', 'datafast'),
            ('provider_id.state', 'in', ('test', 'enabled')),
            ('state', 'in', ('draft', 'pending')),
            ('provider_reference', '!=', False),
            ('create_date', '<=', cutoff),
        ])
        for transaction in transactions:
            try:
                transaction._datafast_verify()
            except ValidationError as error:
                _logger.warning(
                    'Datafast verification retry failed for %s: %s',
                    transaction.reference,
                    error,
                )

    def action_datafast_verify(self):
        self.ensure_one()
        self._datafast_verify()
        return True

    @api.model
    def _extract_reference(self, provider_code, payment_data):
        if provider_code == 'datafast':
            return payment_data.get('merchantTransactionId') or payment_data.get('reference')
        return super()._extract_reference(provider_code, payment_data)

    def _extract_amount_data(self, payment_data):
        if self.provider_code != 'datafast':
            return super()._extract_amount_data(payment_data)
        return {
            'amount': float(payment_data.get('amount') or 0),
            'currency_code': payment_data.get('currency'),
        }

    def _apply_updates(self, payment_data):
        super()._apply_updates(payment_data)
        if self.provider_code != 'datafast':
            return

        result = payment_data.get('result') or {}
        code = result.get('code') or ''
        self.provider_reference = payment_data.get('id') or self.provider_reference
        message = result.get('description') or _('No description returned by Datafast.')

        if code.startswith('000.200'):
            self._set_pending(state_message=message)
        elif code.startswith('000.'):
            if self.tokenize and not payment_data.get('registrationId'):
                _logger.warning(
                    'Datafast completed transaction %s without a registrationId.', self.reference
                )
                self.tokenize = False
            self._set_done(state_message=message)
            if self.operation == 'refund':
                self.env.ref('payment.cron_post_process_payment_tx')._trigger()
        else:
            self._set_error(message, extra_allowed_states=('done',) if self.operation == 'refund' else ())

    def _extract_token_values(self, payment_data):
        if self.provider_code != 'datafast':
            return super()._extract_token_values(payment_data)
        registration_id = payment_data.get('registrationId')
        if not registration_id:
            return {}
        card = payment_data.get('card') or {}
        brand = payment_data.get('paymentBrand') or card.get('brand') or 'Card'
        last4 = card.get('last4Digits') or card.get('last4digits') or card.get('last4') or ''
        return {
            'provider_ref': registration_id,
            'payment_details': f'{brand} **** {last4}' if last4 else brand,
        }

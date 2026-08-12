/** @odoo-module **/

import { patch } from '@web/core/utils/patch';
import { PaymentForm } from '@payment/interactions/payment_form';

patch(PaymentForm.prototype, {
    _loadPayphoneBoxSdk() {
        if (window.PPaymentButtonBox) {
            return Promise.resolve();
        }
        if (window.__payphoneBoxSdkPromise) {
            return window.__payphoneBoxSdkPromise;
        }
        window.__payphoneBoxSdkPromise = new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.type = 'module';
            script.src = 'https://cdn.payphonetodoesposible.com/box/v2.0/payphone-payment-box.js';
            document.head.appendChild(script);
            const startedAt = Date.now();
            const waitForSdk = () => {
                if (window.PPaymentButtonBox) {
                    resolve();
                } else if (Date.now() - startedAt > 10000) {
                    reject(new Error('No se pudo cargar la Cajita de Pagos PayPhone.'));
                } else {
                    window.setTimeout(waitForSdk, 100);
                }
            };
            waitForSdk();
        });
        return window.__payphoneBoxSdkPromise;
    },

    async _prepareInlineForm(providerId, providerCode, paymentOptionId, paymentMethodCode, flow) {
        if (providerCode !== 'payphone' || paymentMethodCode !== 'payphone_box') {
            await super._prepareInlineForm(...arguments);
            return;
        }
        if (flow === 'token') {
            return;
        }
        this._setPaymentFlow('direct');
    },

    async _processDirectFlow(providerCode, paymentOptionId, paymentMethodCode, processingValues) {
        if (providerCode !== 'payphone' || !processingValues.payphone_box) {
            await super._processDirectFlow(...arguments);
            return;
        }
        const wrapper = this.el.querySelector('[data-payphone-box="1"]');
        const container = wrapper && wrapper.querySelector('.o_payphone_box');
        if (!container) {
            this._displayErrorDialog('Pago PayPhone', 'No se encontró el contenedor de la Cajita PayPhone.');
            this._enableButton();
            return;
        }
        try {
            await this._loadPayphoneBoxSdk();
            const targetId = 'payphone-box-' + String(processingValues.reference)
                .replace(/[^a-zA-Z0-9_-]/g, '-');
            container.id = targetId;
            container.innerHTML = '';
            new window.PPaymentButtonBox({
                token: processingValues.payphone_box_token,
                storeId: processingValues.payphone_box_store_id,
                clientTransactionId: processingValues.payphone_box_reference,
                amount: processingValues.payphone_box_amount,
                amountWithoutTax: processingValues.payphone_box_amount,
                amountWithTax: 0,
                tax: 0,
                service: 0,
                tip: 0,
                currency: processingValues.payphone_box_currency,
                reference: processingValues.payphone_box_reference,
                lang: 'es',
                timeZone: -5,
            }).render(targetId);
            window.setTimeout(() => {
                const payButton = [...container.querySelectorAll('button')]
                    .find(button => /pagar/i.test(button.textContent || ''));
                if (payButton) {
                    payButton.click();
                }
            }, 300);
        } catch (error) {
            this._displayErrorDialog('Pago PayPhone', error.message || String(error));
            this._enableButton();
        }
    },

    async submitForm(ev) {
        const checkedRadio = this.el.querySelector('input[name="o_payment_radio"]:checked');
        const isPayphoneRedirect = checkedRadio
            && this._getProviderCode(checkedRadio) === 'payphone'
            && this._getPaymentMethodCode(checkedRadio) !== 'payphone_box';
        if (isPayphoneRedirect) {
            this.payphonePaymentWindowName = 'payphone_payment_' + Date.now();
            this.payphonePaymentWindow = window.open('', this.payphonePaymentWindowName);
            this.payphonePaymentWindow?.focus();
        }
        await super.submitForm(...arguments);
    },

    _processRedirectFlow(providerCode, paymentOptionId, paymentMethodCode, processingValues) {
        if (providerCode !== 'payphone') {
            super._processRedirectFlow(...arguments);
            return;
        }
        const div = document.createElement('div');
        div.innerHTML = processingValues.redirect_form_html || '';
        const redirectForm = div.querySelector('form');
        if (!redirectForm) {
            super._processRedirectFlow(...arguments);
            return;
        }
        const reference = redirectForm.querySelector('input[name="reference"]')?.value;
        const popup = this.payphonePaymentWindow;
        redirectForm.setAttribute('target', popup && !popup.closed ? this.payphonePaymentWindowName : '_blank');
        redirectForm.setAttribute('id', 'o_payment_redirect_form');
        document.body.appendChild(redirectForm);
        redirectForm.submit();
        if (!reference) {
            return;
        }
        const pollUrl = '/payment/payphone/status?reference=' + encodeURIComponent(reference);
        const poll = window.setInterval(async () => {
            try {
                const response = await fetch(pollUrl, { credentials: 'same-origin' });
                const data = await response.json();
                if (['done', 'cancel', 'error'].includes(data.state)) {
                    window.clearInterval(poll);
                    window.location.href = '/payment/status';
                }
            } catch {
                // Keep polling while the payment provider is processing the transaction.
            }
        }, 2000);
    },
});

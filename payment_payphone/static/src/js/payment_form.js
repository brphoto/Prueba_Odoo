/** @odoo-module **/

import publicWidget from '@web/legacy/js/public/public_widget';

publicWidget.registry.PaymentForm.include({
    _isPayphoneBox(paymentMethodCode) {
        if (paymentMethodCode === 'payphone_box') {
            return true;
        }
        const selected = this.el.querySelector('input[name="o_payment_radio"]:checked');
        return (selected && selected.dataset.paymentMethodCode === 'payphone_box')
            || Boolean(this.el.querySelector('[data-payphone-box="1"]'));
    },

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
        if (providerCode !== 'payphone' || !this._isPayphoneBox(paymentMethodCode)) {
            return this._super(...arguments);
        }
        if (flow === 'token') {
            return;
        }
        this._setPaymentFlow('direct');
    },

    async _processDirectFlow(providerCode, paymentOptionId, paymentMethodCode, processingValues) {
        if (providerCode !== 'payphone' || !processingValues.payphone_box) {
            return this._super(...arguments);
        }
        const wrapper = this.el.querySelector('[data-payphone-box="1"]');
        const container = wrapper && wrapper.querySelector('.o_payphone_box');
        if (!container) {
            throw new Error('No se encontró el contenedor de la Cajita PayPhone.');
        }
        try {
            await this._loadPayphoneBoxSdk();
            const targetId = 'payphone-box-' + String(processingValues.reference).replace(/[^a-zA-Z0-9_-]/g, '-');
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
            if (this._displayErrorDialog) {
                this._displayErrorDialog('Pago PayPhone', error.message || String(error));
            }
            if (this._enableButton) {
                this._enableButton();
            }
        }
    },

    _submitForm(ev) {
        const checkedRadio = this.el.querySelector('input[name="o_payment_radio"]:checked');
        if (checkedRadio && this._getProviderCode(checkedRadio) === 'payphone'
            && checkedRadio.dataset.paymentMethodCode !== 'payphone_box') {
            // Open the payment window from the user click to avoid popup blockers.
            this.payphonePaymentWindowName = 'payphone_payment_' + Date.now();
            // Without window features Chrome opens a real browser tab instead
            // of a separate popup window.
            this.payphonePaymentWindow = window.open('', this.payphonePaymentWindowName);
            if (this.payphonePaymentWindow) {
                this.payphonePaymentWindow.document.title = 'PayPhone';
                this.payphonePaymentWindow.focus();
            }
        }
        return this._super(...arguments);
    },

    _processRedirectFlow(providerCode, paymentOptionId, paymentMethodCode, processingValues) {
        if (providerCode !== 'payphone') {
            return this._super(...arguments);
        }

        const container = document.createElement('div');
        container.innerHTML = processingValues.redirect_form_html || '';
        const redirectForm = container.querySelector('form');
        if (!redirectForm) {
            return this._super(...arguments);
        }

        const referenceInput = redirectForm.querySelector('input[name="reference"]');
        const reference = referenceInput && referenceInput.value;
        const popup = this.payphonePaymentWindow;
        if (popup && !popup.closed) {
            redirectForm.setAttribute('target', this.payphonePaymentWindowName);
            popup.focus();
        } else {
            redirectForm.setAttribute('target', '_blank');
        }
        redirectForm.setAttribute('id', 'o_payment_redirect_form');
        document.body.appendChild(redirectForm);
        redirectForm.submit();

        if (reference) {
            const pollUrl = '/payment/payphone/status?reference=' + encodeURIComponent(reference);
            const checkPayment = () => fetch(pollUrl, {credentials: 'same-origin'})
                .then(response => response.json())
                .then(data => {
                    if (['done', 'cancel', 'error'].includes(data.state)) {
                        window.clearInterval(poll);
                        window.location.href = '/payment/status';
                    }
                })
                .catch(() => {});
            const poll = window.setInterval(() => {
                // Closing the window does not approve the payment. The server
                // must confirm the transaction before Odoo changes its state.
                checkPayment();
            }, 2000);
            if (popup) {
                const closeWatcher = window.setInterval(() => {
                    if (popup.closed) {
                        window.clearInterval(closeWatcher);
                        checkPayment();
                    }
                }, 500);
            }
        }
    },
});

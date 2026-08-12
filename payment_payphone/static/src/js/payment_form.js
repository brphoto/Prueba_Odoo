/** @odoo-module **/

import publicWidget from '@web/legacy/js/public/public_widget';

publicWidget.registry.PaymentForm.include({
    _submitForm(ev) {
        const checkedRadio = this.el.querySelector('input[name="o_payment_radio"]:checked');
        if (checkedRadio && this._getProviderCode(checkedRadio) === 'payphone') {
            // Open the payment window from the user click to avoid popup blockers.
            this.payphonePaymentWindowName = 'payphone_payment_' + Date.now();
            this.payphonePaymentWindow = window.open(
                '',
                this.payphonePaymentWindowName,
                'popup=yes,width=560,height=760,resizable=yes,scrollbars=yes'
            );
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

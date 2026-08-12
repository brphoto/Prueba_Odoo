/** @odoo-module **/

import publicWidget from '@web/legacy/js/public/public_widget';

publicWidget.registry.PaymentForm.include({
    /** Keep checkout open while PayPhone is displayed in a separate tab. */
    _submitForm(ev) {
        const checkedRadio = this.el.querySelector('input[name="o_payment_radio"]:checked');
        if (checkedRadio && this._getProviderCode(checkedRadio) === 'payphone') {
            // Open the tab directly from the click event to avoid popup blockers after the RPC.
            this.payphonePaymentWindow = window.open('', 'payphone_payment');
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
            redirectForm.setAttribute('target', 'payphone_payment');
        } else {
            redirectForm.setAttribute('target', '_blank');
        }
        redirectForm.setAttribute('id', 'o_payment_redirect_form');
        document.body.appendChild(redirectForm);
        redirectForm.submit();

        if (reference) {
            const pollUrl = '/payment/payphone/status?reference=' + encodeURIComponent(reference);
            const poll = window.setInterval(() => {
                fetch(pollUrl, {credentials: 'same-origin'})
                    .then(response => response.json())
                    .then(data => {
                        if (['done', 'cancel', 'error'].includes(data.state)) {
                            window.clearInterval(poll);
                            window.location.href = '/payment/status';
                        }
                    })
                    .catch(() => {});
            }, 3000);
        }
    },
});

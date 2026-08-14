import { loadJS } from '@web/core/assets';
import { patch } from '@web/core/utils/patch';

import { PaymentForm } from '@payment/interactions/payment_form';

patch(PaymentForm.prototype, {
    async _prepareInlineForm(providerId, providerCode, paymentOptionId, paymentMethodCode, flow) {
        if (providerCode !== 'datafast') {
            await super._prepareInlineForm(...arguments);
            return;
        }
        if (flow !== 'token') {
            this._setPaymentFlow('direct');
        }
    },

    async _processDirectFlow(providerCode, paymentOptionId, paymentMethodCode, processingValues) {
        if (providerCode !== 'datafast') {
            await super._processDirectFlow(...arguments);
            return;
        }

        const radio = this.el.querySelector('input[name="o_payment_radio"]:checked');
        const inlineForm = this._getInlineForm(radio);
        if (!inlineForm) {
            return;
        }
        inlineForm.innerHTML = '';

        const enableTokenization = Boolean(processingValues.datafast_tokenization_enabled);
        const optionsScript = document.createElement('script');
        optionsScript.text = `window.wpwlOptions = {
            style: 'card',
            locale: 'es',
            labels: { cvv: 'Código de verificación', cardholder: 'Nombre (igual que en la tarjeta)' },
            registrations: { requireCvv: true, hideInitialPaymentForms: true },
            onReady: function() {
                if (!${enableTokenization ? 'true' : 'false'}) {
                    return;
                }
                var form = document.querySelector('form.wpwl-form-card');
                if (!form || form.querySelector('[name="createRegistration"]')) {
                    return;
                }
                var wrapper = document.createElement('div');
                wrapper.className = 'datafast-registration-option';
                wrapper.innerHTML = '<label><input type="checkbox" name="createRegistration" checked="checked" /> ' +
                    'Guardar esta tarjeta de forma segura para futuras compras</label>';
                var button = form.querySelector('.wpwl-button');
                if (button) {
                    button.parentNode.insertBefore(wrapper, button);
                } else {
                    form.appendChild(wrapper);
                }
            }
        };`;

        const paymentWidget = document.createElement('form');
        paymentWidget.action = processingValues.datafast_shopper_result_url;
        paymentWidget.className = 'paymentWidgets';
        paymentWidget.dataset.brands = processingValues.datafast_brands;

        inlineForm.appendChild(optionsScript);
        inlineForm.appendChild(paymentWidget);
        await this.waitFor(loadJS(
            `${processingValues.datafast_widget_url}?checkoutId=${encodeURIComponent(
                processingValues.datafast_checkout_id
            )}`
        ));

        if (!document.querySelector('script[data-datafast-validations]')) {
            const validationsScript = document.createElement('script');
            validationsScript.src = 'https://www.datafast.com.ec/js/dfAdditionalValidations1.js';
            validationsScript.dataset.datafastValidations = 'true';
            document.body.appendChild(validationsScript);
        }
        this._hideInputs();
    },
});

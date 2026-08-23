/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ContactPanel } from "@chatroom_whatsapp/chatroom_app/contact_panel";

patch(ContactPanel.prototype, {
    paymentStateLabel(state) {
        return {
            generated: 'Generado',
            sent: 'Enviado',
            paid: 'Pagado',
            expired: 'Expirado',
            error: 'Error',
        }[state] || state || '';
    },

    async sendOrderPaymentLink(order) {
        await this._sendPaymentLink(`order-pay-${order.id}`, "sale.order", order.id);
    },

    async sendInvoicePaymentLink(invoice) {
        await this._sendPaymentLink(`invoice-pay-${invoice.id}`, "account.move", invoice.id);
    },

    async _sendPaymentLink(key, resModel, resId) {
        if (this.state.sendingDocKey) {
            return;
        }
        this.state.sendingDocKey = key;
        try {
            await this.orm.call(
                "chatroom.channel", "action_send_payment_link",
                [this.props.channelId, resModel, resId]);
            this.notification.add("Link de pago enviado por WhatsApp.", { type: "success" });
        } catch (error) {
            this.notification.add(error.data ? error.data.message : error.message, {
                type: "danger",
            });
        } finally {
            this.state.sendingDocKey = false;
        }
    },
});

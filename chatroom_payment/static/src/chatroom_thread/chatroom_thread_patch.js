/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ChatroomThreadCore } from "@chatroom_whatsapp/chatroom_thread/chatroom_thread_core";

patch(ChatroomThreadCore.prototype, {
    async openPaymentWizard() {
        try {
            const action = await this.orm.call(
                "chatroom.channel", "action_open_payment_wizard", [this.channelId]);
            this.action.doAction({ ...action, target: "new" }, {
                onClose: () => this._loadMessages(),
            });
        } catch (error) {
            this.notification.add(error.data ? error.data.message : error.message, {
                type: "danger",
            });
        }
    },
});

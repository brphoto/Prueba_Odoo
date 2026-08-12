/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ChatroomThreadCore } from "@chatroom_whatsapp/chatroom_thread/chatroom_thread_core";

patch(ChatroomThreadCore.prototype, {
    async createMeetAndSend() {
        try {
            await this.orm.call(
                "chatroom.channel", "action_create_meet_and_send", [this.channelId]);
            this.notification.add("Enlace de reunión enviado al chat.", { type: "success" });
            await this._loadMessages();
        } catch (error) {
            this.notification.add(error.data ? error.data.message : error.message, {
                type: "danger",
            });
        }
    },
});

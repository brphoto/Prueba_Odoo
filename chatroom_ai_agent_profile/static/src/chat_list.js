/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ChatroomApp } from "@chatroom_whatsapp/chatroom_app/chatroom_app";

const AI_STATES = {
    ai: { icon: "fa-magic", label: "Respondió la IA", css: "o_ai_state_ai" },
    draft: { icon: "fa-hourglass-half", label: "Borrador por aprobar", css: "o_ai_state_draft" },
    human: { icon: "fa-user", label: "Con una persona", css: "o_ai_state_human" },
};

patch(ChatroomApp.prototype, {
    channelFields() {
        return [...super.channelFields(), "ai_list_state"];
    },

    aiListState(channel) {
        return AI_STATES[channel.ai_list_state] || false;
    },
});

/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ContactPanel } from "@chatroom_whatsapp/chatroom_app/contact_panel";

patch(ContactPanel.prototype, {
    setup() {
        super.setup();
        this.aiAssistant.playbook = false;
        this.aiAssistant.canTakeOver = false;
    },

    _applyAiAssistantData(data) {
        super._applyAiAssistantData(data);
        this.aiAssistant.playbook = data?.playbook || false;
        this.aiAssistant.canTakeOver = Boolean(data?.can_take_over);
    },

    async takeOverConversation() {
        const data = await this.orm.call(
            "chatroom.channel", "action_ai_take_over", [[this.props.channelId]]);
        this._applyAiAssistantData(data);
        this.env.services.notification.add("La conversación quedó a tu cargo; la IA está en pausa.", {
            type: "success",
        });
    },

    aiPlaybookTitle() {
        const playbook = this.aiAssistant.playbook;
        if (!playbook || playbook.done || !playbook.missing.length) {
            return "";
        }
        return `Falta: ${playbook.missing.join(", ")}`;
    },

    async resetAiPlaybook() {
        const data = await this.orm.call(
            "chatroom.channel", "action_ai_reset_playbook", [[this.props.channelId]]);
        this._applyAiAssistantData(data);
    },
});

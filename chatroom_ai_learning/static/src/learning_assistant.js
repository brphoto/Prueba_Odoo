/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ContactPanel } from "@chatroom_whatsapp/chatroom_app/contact_panel";

patch(ContactPanel.prototype, {
    setup() {
        super.setup();
        this.aiAssistant.autonomyLevel = false;
        this.aiAssistant.handoffReason = "";
    },

    _applyAiAssistantData(data) {
        super._applyAiAssistantData(data);
        this.aiAssistant.autonomyLevel = data?.autonomy_level || false;
        this.aiAssistant.handoffReason = data?.handoff_reason || "";
    },

    aiAutonomyClass() {
        const state = this.aiAssistant.autonomyLevel?.state;
        if (state === "automatic" && this.aiAssistant.autonomyLevel.automatic) {
            return "text-bg-success";
        }
        if (state === "blocked") {
            return "text-bg-danger";
        }
        return "text-bg-info";
    },

    aiAutonomyLabel() {
        const autonomy = this.aiAssistant.autonomyLevel;
        if (!autonomy) {
            return "";
        }
        if (autonomy.state === "automatic" && !autonomy.automatic) {
            return "Supervisado (autonomía congelada)";
        }
        return autonomy.state_label;
    },
});

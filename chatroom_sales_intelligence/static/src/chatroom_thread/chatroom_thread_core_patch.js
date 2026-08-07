/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { useState } from "@odoo/owl";
import { ChatroomThreadCore } from "@chatroom_whatsapp/chatroom_thread/chatroom_thread_core";
import { ChatroomIntelligencePanel } from "./chatroom_intelligence_panel";

patch(ChatroomThreadCore, {
    components: { ...ChatroomThreadCore.components, ChatroomIntelligencePanel },
});

const RFM_LABELS = { a: "A", b: "B", c: "C" };

patch(ChatroomThreadCore.prototype, {
    setup() {
        super.setup();
        this.intel = useState({
            rfmCategory: false,
            managementAlertState: "green",
            managementDaysStagnant: 0,
            panelOpen: false,
            loading: false,
            generating: false,
            data: false,
        });
        this._touchStartX = null;
    },

    async _loadChannel(channelId = this.channelId) {
        await super._loadChannel(channelId);
        if (!channelId) {
            this.intel.rfmCategory = false;
            this.intel.managementAlertState = "green";
            this.intel.managementDaysStagnant = 0;
            this.intel.data = false;
            return;
        }
        const [channel] = await this.orm.read(
            "chatroom.channel", [channelId],
            ["rfm_category", "management_alert_state", "management_days_stagnant"]
        );
        this.intel.rfmCategory = channel.rfm_category;
        this.intel.managementAlertState = channel.management_alert_state;
        this.intel.managementDaysStagnant = channel.management_days_stagnant;
        this.intel.data = false;
        if (this.intel.panelOpen) {
            await this._loadIntelligenceData(channelId);
        }
    },

    rfmBadgeLabel(category) {
        return RFM_LABELS[category] || "";
    },

    async toggleIntelligencePanel() {
        this.intel.panelOpen = !this.intel.panelOpen;
        if (this.intel.panelOpen && !this.intel.data) {
            await this._loadIntelligenceData();
        }
    },

    closeIntelligencePanel() {
        this.intel.panelOpen = false;
    },

    async _loadIntelligenceData(channelId = this.channelId) {
        if (!channelId) {
            return;
        }
        this.intel.loading = true;
        try {
            this.intel.data = await this.orm.call(
                "chatroom.channel", "get_commercial_intelligence", [channelId]);
        } finally {
            this.intel.loading = false;
        }
    },

    _focusComposer() {
        const container = this.messagesRef.el && this.messagesRef.el.closest(".o_chatroom_thread");
        const textarea = container && container.querySelector(".o_chatroom_composer_textarea");
        if (textarea) {
            textarea.focus();
        }
    },

    focusComposerForFollowup() {
        this._focusComposer();
    },

    async generateFollowup() {
        if (!this.channelId) {
            return;
        }
        this.intel.generating = true;
        try {
            const suggestion = await this.orm.call(
                "chatroom.channel", "action_ai_generate_followup", [this.channelId]);
            this.state.composerText = suggestion;
            this.intel.panelOpen = false;
            this._focusComposer();
        } catch (error) {
            this.notification.add(error.data ? error.data.message : error.message, {
                type: "danger",
            });
        } finally {
            this.intel.generating = false;
        }
    },

    // ------------------------------------------------------------------
    // Gesto de deslizar (swipe) sobre el área de mensajes para abrir/cerrar
    // el panel lateral, igual que el perfil de un chat en WhatsApp. Se
    // complementa (no reemplaza) con el botón visible del borde derecho,
    // para que también funcione con mouse/teclado.
    // ------------------------------------------------------------------
    onThreadTouchStart(ev) {
        this._touchStartX = ev.touches[0].clientX;
    },

    onThreadTouchEnd(ev) {
        if (this._touchStartX === null) {
            return;
        }
        const deltaX = ev.changedTouches[0].clientX - this._touchStartX;
        this._touchStartX = null;
        if (Math.abs(deltaX) < 60) {
            return;
        }
        if (deltaX < 0 && !this.intel.panelOpen) {
            this.toggleIntelligencePanel();
        } else if (deltaX > 0 && this.intel.panelOpen) {
            this.closeIntelligencePanel();
        }
    },
});

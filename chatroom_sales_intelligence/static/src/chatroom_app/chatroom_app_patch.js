/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { useState, onWillUpdateProps } from "@odoo/owl";
import { ChatroomApp } from "@chatroom_whatsapp/chatroom_app/chatroom_app";
import { ContactPanel } from "@chatroom_whatsapp/chatroom_app/contact_panel";
import { ChatroomIntelligencePanel } from "../chatroom_thread/chatroom_intelligence_panel";

/**
 * Agrega la categoría RFM y la alerta de seguimiento a la lista de
 * conversaciones de la app de una sola pantalla. Se hace con una segunda
 * lectura liviana después de la carga normal, en vez de tocar el domain
 * o los campos de _loadChannels en chatroom_whatsapp, para no acoplarse
 * a los detalles internos de ese método.
 */
patch(ChatroomApp.prototype, {
    async _loadChannels() {
        await super._loadChannels();
        const ids = this.state.channels.map((c) => c.id);
        if (!ids.length) {
            return;
        }
        const extra = await this.orm.read(
            "chatroom.channel", ids, ["rfm_category", "management_alert_state"]);
        const byId = Object.fromEntries(extra.map((e) => [e.id, e]));
        this.state.channels = this.state.channels.map((c) => ({
            ...c,
            rfm_category: byId[c.id] ? byId[c.id].rfm_category : false,
            management_alert_state: byId[c.id] ? byId[c.id].management_alert_state : "green",
        }));
    },
});

// La inteligencia comparte el mismo lateral que los datos del contacto y
// las acciones comerciales. Así en escritorio y móvil hay una sola ficha,
// en vez de dos paneles absolutos que se pisan entre sí.
patch(ContactPanel, {
    components: { ...ContactPanel.components, ChatroomIntelligencePanel },
});

patch(ContactPanel.prototype, {
    setup() {
        super.setup();
        this.intel = useState({
            panelOpen: false,
            loading: false,
            generating: false,
            data: false,
            assignmentHistory: [],
        });
        onWillUpdateProps((nextProps) => {
            if (nextProps.channelId !== this.props.channelId) {
                this.intel.panelOpen = false;
                this.intel.data = false;
                this.intel.assignmentHistory = [];
                return this._loadCommercialIntelligence(nextProps.channelId);
            }
        });
    },

    async _loadCommercialIntelligence(channelId = this.props.channelId) {
        if (!channelId) {
            this.intel.data = false;
            return;
        }
        this.intel.loading = true;
        try {
            const [data, assignmentHistory] = await Promise.all([
                this.orm.call(
                    "chatroom.channel", "get_commercial_intelligence", [channelId]),
                this.orm.call(
                    "chatroom.channel", "get_assignment_history", [channelId]),
            ]);
            this.intel.data = data;
            this.intel.assignmentHistory = assignmentHistory;
        } catch (error) {
            this.intel.data = false;
            this.intel.assignmentHistory = [];
            this.notification.add(error.data ? error.data.message : error.message, {
                type: "danger",
            });
        } finally {
            this.intel.loading = false;
        }
    },

    async toggleIntelligencePanel() {
        this.intel.panelOpen = !this.intel.panelOpen;
        if (this.intel.panelOpen && !this.intel.data) {
            await this._loadCommercialIntelligence();
        }
    },

    closeIntelligencePanel() {
        this.intel.panelOpen = false;
    },

    async generateCommercialFollowup() {
        if (!this.props.channelId || this.intel.generating) {
            return;
        }
        this.intel.generating = true;
        try {
            const suggestion = await this.orm.call(
                "chatroom.channel", "action_ai_generate_followup", [this.props.channelId]);
            this.env.bus.trigger("chatroom_intelligence_followup", {
                channelId: this.props.channelId,
                suggestion,
            });
            this.notification.add("Sugerencia preparada en el redactor del chat.", {
                type: "success",
            });
            this.intel.panelOpen = false;
        } catch (error) {
            this.notification.add(error.data ? error.data.message : error.message, {
                type: "danger",
            });
        } finally {
            this.intel.generating = false;
        }
    },
});

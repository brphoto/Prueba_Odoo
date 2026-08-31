/** @odoo-module **/

import {
    Component,
    onMounted,
    onWillStart,
    onWillUnmount,
    onWillUpdateProps,
    useState,
} from "@odoo/owl";
import { Chatter } from "@mail/chatter/web_portal/chatter";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import { ChatroomThreadCore } from "../chatroom_thread/chatroom_thread_core";

function hexToRgba(hex, alpha) {
    const match = /^#([0-9a-f]{6})$/i.exec(hex || "");
    if (!match) {
        return `rgba(0, 168, 132, ${alpha})`;
    }
    const value = parseInt(match[1], 16);
    return `rgba(${value >> 16}, ${(value >> 8) & 255}, ${value & 255}, ${alpha})`;
}

export class ChatroomChatter extends Component {
    static template = "chatroom_whatsapp.ChatroomChatter";
    static components = { ChatroomThreadCore };
    static props = {
        model: String,
        resId: [Number, String],
        thread: { type: Object, optional: true },
        webRecord: { type: Object, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.busService = useService("bus_service");
        this.state = useState({
            loading: true,
            error: false,
            partnerName: "",
            partnerId: false,
            channels: [],
            selectedChannelId: false,
            relatedRecords: [],
            totalUnread: 0,
            aiAvailable: false,
            uiStyle: "",
            aiOpen: false,
            aiBusy: false,
            aiAction: "summary",
            aiError: "",
        });
        this._onBusNotification = this._onBusNotification.bind(this);
        onWillStart(() => this.loadContext());
        onMounted(() => {
            this.busService.addChannel("chatroom_whatsapp_global");
            this.busService.addEventListener("notification", this._onBusNotification);
        });
        onWillUnmount(() => {
            this.busService.removeEventListener("notification", this._onBusNotification);
        });
    }

    async loadContext() {
        this.state.loading = true;
        this.state.error = false;
        try {
            const context = await this.orm.call(
                "chatroom.channel",
                "get_chatter_context",
                [this.props.model, Number(this.props.resId)]
            );
            const previousChannelId = this.state.selectedChannelId;
            this.state.partnerId = context.partner_id || false;
            this.state.partnerName = context.partner_name || "";
            this.state.channels = context.channels || [];
            this.state.relatedRecords = context.related_records || [];
            this.state.totalUnread = context.total_unread || 0;
            this.state.aiAvailable = Boolean(context.ai_available);
            this.state.uiStyle = "";
            // chatroom_ui is optional. Its settings are read only when the
            // extension is installed; the base chatter keeps native Odoo
            // styling when it is not present.
            try {
                const ui = await this.orm.call("chatroom.channel", "get_ui_settings", []);
                this.state.uiStyle = this._buildUiStyle(ui || {});
            } catch (error) {
                this.state.uiStyle = "";
            }
            this.state.selectedChannelId = this.state.channels.some(
                (channel) => channel.id === previousChannelId
            ) ? previousChannelId : (this.state.channels[0]?.id || false);
        } catch (error) {
            // El chatter nunca debe romperse por una regla de acceso de
            // Chatroom. En ese caso se muestra un estado discreto y se
            // mantiene disponible el chatter nativo de Odoo.
            this.state.error = true;
            this.state.channels = [];
            this.state.partnerId = false;
            this.state.relatedRecords = [];
            this.state.totalUnread = 0;
        } finally {
            this.state.loading = false;
        }
    }

    get hasChannels() {
        return this.state.channels.length > 0;
    }

    _buildUiStyle(settings) {
        const variables = {
            "--chatroom-ui-primary": settings.primary_color,
            "--chatroom-ui-primary-deep": settings.secondary_color,
            "--chatroom-ui-accent": settings.accent_color,
            "--chatroom-ui-outgoing-bubble": hexToRgba(settings.accent_color, 0.18),
            "--chatroom-ui-sidebar-width": settings.sidebar_width && `${settings.sidebar_width}px`,
            "--chatroom-ui-icon-scale": settings.icon_scale,
            "--chatroom-ui-font-scale": settings.font_scale,
            "--chatroom-ui-bubble-radius": settings.bubble_radius && `${settings.bubble_radius}px`,
            "--chatroom-ui-message-gap": settings.message_gap,
            "--chatroom-ui-bubble-padding": settings.bubble_padding,
        };
        const style = Object.entries(variables)
            .filter(([, value]) => value !== undefined && value !== null && value !== "")
            .map(([name, value]) => `${name}: ${value}`);
        if (settings.background_image) {
            style.push(`--chatroom-ui-chat-background: url(\"${settings.background_image}\")`);
            style.push("--chatroom-ui-chat-background-size: cover");
            style.push("--chatroom-ui-chat-background-repeat: no-repeat");
        }
        return style.join("; ");
    }

    get channelCount() {
        return this.state.channels.length;
    }

    get selectedChannel() {
        return this.state.channels.find(
            (channel) => channel.id === this.state.selectedChannelId
        );
    }

    channelLabel(channel) {
        const labels = {
            whatsapp: "WhatsApp",
            messenger: "Messenger",
            instagram: "Instagram",
        };
        return labels[channel.channel_type] || "Chatroom";
    }

    formatDate(value) {
        if (!value) {
            return "Sin actividad registrada";
        }
        return String(value).replace(" ", " · ").slice(0, 22);
    }

    async openConversation(channel) {
        this.state.selectedChannelId = channel.id;
        this.state.aiError = "";
    }

    async openNewConversation() {
        if (!this.state.partnerId) {
            return;
        }
        try {
            await this.action.doAction(
                "chatroom_whatsapp.action_chatroom_new_conversation_wizard",
                {
                    additionalContext: { default_partner_id: this.state.partnerId },
                    onClose: () => this.loadContext(),
                }
            );
        } catch (error) {
            this.notification.add("No se pudo iniciar una conversación.", {
                type: "danger",
            });
        }
    }

    async openRelated(record) {
        try {
            await this.action.doAction({
                type: "ir.actions.act_window",
                name: record.label,
                res_model: record.model,
                res_id: record.id,
                views: [[false, "form"]],
                view_mode: "form",
                target: "new",
            });
        } catch (error) {
            this.notification.add("No se pudo abrir el registro relacionado.", {
                type: "danger",
            });
        }
    }

    toggleAi() {
        if (!this.state.aiAvailable) {
            return;
        }
        this.state.aiOpen = !this.state.aiOpen;
        this.state.aiError = "";
    }

    async runAiAction() {
        const channel = this.selectedChannel;
        const methods = {
            summary: "action_ai_summarize",
            reply: "action_ai_suggest_reply",
            intent: "action_ai_classify_intent",
            analysis: "action_ai_analyze",
            next_action: "action_ai_next_action",
        };
        const method = methods[this.state.aiAction];
        if (!channel || !method) {
            return;
        }
        this.state.aiBusy = true;
        this.state.aiError = "";
        try {
            await this.orm.call("chatroom.channel", method, [channel.id]);
            await this.loadContext();
        } catch (error) {
            this.state.aiError = error?.data?.message || error?.message
                || "No se pudo consultar la IA.";
        } finally {
            this.state.aiBusy = false;
        }
    }

    async sendAiSuggestion() {
        const channel = this.selectedChannel;
        if (!channel?.ai_suggested_reply) {
            return;
        }
        this.state.aiBusy = true;
        this.state.aiError = "";
        try {
            await this.orm.call("chatroom.channel", "action_send_ai_suggestion", [channel.id]);
            await this.loadContext();
        } catch (error) {
            this.state.aiError = error?.data?.message || error?.message
                || "No se pudo enviar la sugerencia.";
        } finally {
            this.state.aiBusy = false;
        }
    }

    async createAiActivity() {
        const channel = this.selectedChannel;
        if (!channel?.ai_next_action) {
            return;
        }
        this.state.aiBusy = true;
        this.state.aiError = "";
        try {
            await this.orm.call(
                "chatroom.channel",
                "action_create_followup_activity",
                [channel.id, channel.ai_next_action]
            );
            await this.loadContext();
            this.notification.add("Actividad creada con la próxima acción de IA.", {
                type: "success",
            });
        } catch (error) {
            this.state.aiError = error?.data?.message || error?.message
                || "No se pudo crear la actividad.";
        } finally {
            this.state.aiBusy = false;
        }
    }

    _onBusNotification({ detail: notifications }) {
        if (notifications.some(({ type }) =>
            type === "chatroom.message/new" || type === "chatroom.message/inbound")) {
            this.loadContext();
        }
    }

    async openAllConversations() {
        try {
            await this.action.doAction({
                type: "ir.actions.act_window",
                name: "Conversaciones de Chatroom",
                res_model: "chatroom.channel",
                views: [[false, "list"], [false, "form"]],
                view_mode: "list,form",
                domain: [["partner_id", "=", this.state.partnerId]],
                target: "new",
            });
        } catch (error) {
            this.notification.add("No se pudo abrir la bandeja de Chatroom.", {
                type: "danger",
            });
        }
    }
}

Object.assign(Chatter.components, { ChatroomChatter });

patch(Chatter.prototype, {
    setup() {
        super.setup(...arguments);
        this.chatroomOrm = useService("orm");
        this.chatroomAccess = useState({ enabled: false, available: false });
        onWillStart(async () => {
            try {
                this.chatroomAccess.enabled = await user.hasGroup(
                    "chatroom_whatsapp.group_chatroom_user"
                );
                await this._refreshChatroomAvailability(this.props);
            } catch (error) {
                this.chatroomAccess.enabled = false;
                this.chatroomAccess.available = false;
            }
        });
        onWillUpdateProps((nextProps) => {
            if (
                nextProps.threadModel !== this.props.threadModel
                || nextProps.threadId !== this.props.threadId
            ) {
                this.chatroomAccess.available = false;
                this._refreshChatroomAvailability(nextProps);
            }
        });
    },

    async _refreshChatroomAvailability(props) {
        if (
            !this.chatroomAccess.enabled
            || !props.threadId
            || props.threadModel === "chatroom.channel"
        ) {
            this.chatroomAccess.available = false;
            return;
        }
        try {
            const context = await this.chatroomOrm.call(
                "chatroom.channel",
                "get_chatter_context",
                [props.threadModel, Number(props.threadId)]
            );
            // The server looks for partner_id, commercial_partner_id and
            // other res.partner relations, so this works for future models
            // without adding another frontend patch for each one.
            this.chatroomAccess.available = Boolean(context.partner_id);
        } catch (error) {
            this.chatroomAccess.available = false;
        }
    },

    get chatroomAvailable() {
        return Boolean(
            this.chatroomAccess.enabled
            && this.chatroomAccess.available
        );
    },
});

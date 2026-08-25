/** @odoo-module **/

import { Component, onWillStart, onWillUpdateProps, useState } from "@odoo/owl";
import { Chatter } from "@mail/chatter/web_portal/chatter";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import { ChatroomThreadCore } from "../chatroom_thread/chatroom_thread_core";

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
        this.state = useState({
            loading: true,
            error: false,
            partnerName: "",
            partnerId: false,
            channels: [],
            selectedChannelId: false,
        });
        onWillStart(() => this.loadContext());
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
            this.state.partnerId = context.partner_id || false;
            this.state.partnerName = context.partner_name || "";
            this.state.channels = context.channels || [];
            this.state.selectedChannelId = this.state.channels[0]?.id || false;
        } catch (error) {
            // El chatter nunca debe romperse por una regla de acceso de
            // Chatroom. En ese caso se muestra un estado discreto y se
            // mantiene disponible el chatter nativo de Odoo.
            this.state.error = true;
            this.state.channels = [];
            this.state.partnerId = false;
        } finally {
            this.state.loading = false;
        }
    }

    get hasChannels() {
        return this.state.channels.length > 0;
    }

    get channelCount() {
        return this.state.channels.length;
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

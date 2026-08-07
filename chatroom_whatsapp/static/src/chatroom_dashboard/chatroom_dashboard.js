/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onWillStart } from "@odoo/owl";

/**
 * Dashboard de un vistazo: KPIs del día + ranking de agentes. Los números
 * se calculan en el servidor (chatroom.channel.get_dashboard_data, con
 * read_group) para no traer registros de más al navegador.
 */
export class ChatroomDashboard extends Component {
    static template = "chatroom_whatsapp.ChatroomDashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        this.state = useState({
            loading: true,
            pendingCount: 0,
            todayCount: 0,
            messagesToday: 0,
            unreadTotal: 0,
            avgFirstResponseMinutes: 0,
            byAgent: [],
            responseByAgent: [],
            lastWebhookDisplay: "",
            lastWebhookOk: true,
        });

        onWillStart(() => this._loadData());
    }

    async _loadData() {
        this.state.loading = true;
        const data = await this.orm.call("chatroom.channel", "get_dashboard_data", []);
        this.state.pendingCount = data.pending_count;
        this.state.todayCount = data.today_count;
        this.state.messagesToday = data.messages_today;
        this.state.unreadTotal = data.unread_total;
        this.state.avgFirstResponseMinutes = data.avg_first_response_minutes;
        this.state.byAgent = data.by_agent;
        this.state.responseByAgent = data.response_by_agent;
        this.state.lastWebhookDisplay = data.last_webhook_display;
        this.state.lastWebhookOk = data.last_webhook_ok;
        this.state.loading = false;
    }

    openSettings() {
        this.action.doAction("base_setup.action_general_configuration");
    }

    formatMinutes(minutes) {
        if (minutes < 60) {
            return `${minutes} min`;
        }
        const hours = Math.floor(minutes / 60);
        const rest = Math.round(minutes % 60);
        return `${hours} h ${rest} min`;
    }

    barWidth(value, list, key) {
        const max = Math.max(...list.map((item) => item[key]), 1);
        return Math.max(6, Math.round((value / max) * 100));
    }

    openPending() {
        this.action.doAction("chatroom_whatsapp.action_chatroom_channel", {
            additionalContext: { search_default_pending: 1 },
        });
    }

    openUnread() {
        this.action.doAction("chatroom_whatsapp.action_chatroom_channel", {
            additionalContext: { search_default_unread: 1 },
        });
    }

    openToday() {
        this.action.doAction("chatroom_whatsapp.action_chatroom_channel");
    }
}

registry.category("actions").add("chatroom_whatsapp.chatroom_dashboard", ChatroomDashboard);

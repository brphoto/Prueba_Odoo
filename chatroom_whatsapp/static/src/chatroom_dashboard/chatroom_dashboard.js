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
            periodDays: 30,
            periodLabel: "Últimos 30 días",
            pendingCount: 0,
            todayCount: 0,
            messagesToday: 0,
            unreadTotal: 0,
            avgFirstResponseMinutes: 0,
            byAgent: [],
            responseByAgent: [],
            lastWebhookDisplay: "",
            lastWebhookOk: true,
            slaComplianceRate: null,
            slaAnsweredCount: 0,
            avgCsatScore: 0,
            csatAnsweredCount: 0,
            customKpis: [],
            stageBreakdown: [],
            dashboardWidgets: [],
            profiles: [],
            profileId: false,
            profileWidgetIds: false,
        });

        onWillStart(async () => {
            await this.loadProfiles();
            await this._loadData();
        });
    }

    async _loadData() {
        this.state.loading = true;
        const data = await this.orm.call("chatroom.channel", "get_dashboard_data", [
            this.state.periodDays, 8, true, this.state.profileWidgetIds || false,
        ]);
        this.state.periodLabel = data.period_label;
        this.state.pendingCount = data.pending_count;
        this.state.todayCount = data.today_count;
        this.state.messagesToday = data.messages_today;
        this.state.unreadTotal = data.unread_total;
        this.state.avgFirstResponseMinutes = data.avg_first_response_minutes;
        this.state.byAgent = data.by_agent;
        this.state.responseByAgent = data.response_by_agent;
        this.state.lastWebhookDisplay = data.last_webhook_display;
        this.state.lastWebhookOk = data.last_webhook_ok;
        this.state.slaComplianceRate = data.sla_compliance_rate;
        this.state.slaAnsweredCount = data.sla_answered_count;
        this.state.avgCsatScore = data.avg_csat_score;
        this.state.csatAnsweredCount = data.csat_answered_count;
        this.state.customKpis = data.custom_kpis || [];
        this.state.stageBreakdown = data.stage_breakdown || [];
        this.state.dashboardWidgets = data.dashboard_widgets || [];
        this.state.loading = false;
    }

    async changePeriod(ev) {
        this.state.periodDays = Number(ev.target.value);
        await this._loadData();
    }

    async loadProfiles() {
        this.state.profiles = await this.orm.call(
            "chatroom.dashboard.profile", "get_available_profiles", ["chatroom"]);
    }

    async changeProfile(ev) {
        const profile = this.state.profiles.find((item) => item.id === Number(ev.target.value));
        if (!profile) {
            this.state.profileId = false;
            this.state.profileWidgetIds = false;
            return this._loadData();
        }
        this.state.profileId = profile.id;
        this.state.periodDays = profile.period_days;
        this.state.profileWidgetIds = profile.widget_ids;
        await this._loadData();
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

    openCustomKpi(kpi) {
        if (!kpi || !kpi.model) {
            return;
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            name: kpi.name,
            res_model: kpi.model,
            views: [[false, "list"], [false, "form"]],
            domain: kpi.domain || [],
            target: "current",
        });
    }

    openStage(stage) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: stage.name,
            res_model: "chatroom.channel",
            views: [[false, "kanban"], [false, "list"], [false, "form"]],
            domain: [["stage_id", "=", stage.id]],
            target: "current",
        });
    }

    openKpiConfigurator() {
        this.action.doAction("chatroom_whatsapp.action_chatroom_kpi_definition");
    }

    openReportWizard() {
        this.action.doAction("chatroom_whatsapp.action_chatroom_dashboard_report_wizard");
    }

    openWidgetConfigurator() {
        this.action.doAction("chatroom_whatsapp.action_chatroom_dashboard_widget");
    }

    widgetBarWidth(value, points) {
        const max = Math.max(...points.map((point) => Math.abs(point.value || 0)), 1);
        return Math.max(6, Math.round((Math.abs(value || 0) / max) * 100));
    }

    widgetPieStyle(widget) {
        const points = widget.points || [];
        const total = points.reduce((sum, point) => sum + Math.abs(point.value || 0), 0) || 1;
        let cursor = 0;
        const colors = [widget.color || "#714B67", "#00A09D", "#F0A429", "#D9534F", "#6C8EBF", "#6BAA75"];
        const slices = points.map((point, index) => {
            const start = cursor;
            cursor += (Math.abs(point.value || 0) / total) * 100;
            return `${colors[index % colors.length]} ${start}% ${cursor}%`;
        });
        return `background: conic-gradient(${slices.join(", ") || "#283842 0 100%"})`;
    }

    widgetLinePoints(widget) {
        const points = widget.points || [];
        const max = Math.max(...points.map((point) => Number(point.value || 0)), 1);
        const width = 320;
        const height = 110;
        return points.map((point, index) => {
            const x = points.length === 1 ? width / 2 : (index / (points.length - 1)) * width;
            const y = height - (Number(point.value || 0) / max) * (height - 12) - 6;
            return `${x},${y}`;
        }).join(" ");
    }
}

registry.category("actions").add("chatroom_whatsapp.chatroom_dashboard", ChatroomDashboard);

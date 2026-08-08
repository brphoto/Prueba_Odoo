/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";

export class ExecutiveDashboard extends Component {
    static template = "chatroom_sales_intelligence.ExecutiveDashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ loading: true, period: "30", chat: false, rfm: false });
        onWillStart(() => this.loadData());
    }

    async loadData() {
        this.state.loading = true;
        const chatPeriod = this.state.period === "all" ? 0 : Number(this.state.period);
        const [chat, rfm] = await Promise.all([
            this.orm.call("chatroom.channel", "get_dashboard_data", [chatPeriod]),
            this.orm.call("res.partner", "get_rfm_dashboard_data", [this.state.period, "all"]),
        ]);
        this.state.chat = chat;
        this.state.rfm = rfm;
        this.state.loading = false;
    }

    async changePeriod(ev) {
        this.state.period = ev.target.value;
        await this.loadData();
    }

    barWidth(value, rows, key) {
        const max = Math.max(...rows.map((row) => row[key] || 0), 1);
        return Math.max(5, Math.round(((value || 0) / max) * 100));
    }

    openChatroom() {
        this.action.doAction("chatroom_whatsapp.action_chatroom_channel");
    }

    openRfm() {
        this.action.doAction("crm_customer_intelligence.action_customer_intelligence_dashboard");
    }

    openStage(stage) {
        this.action.doAction({
            type: "ir.actions.act_window", name: stage.name,
            res_model: "chatroom.channel",
            views: [[false, "kanban"], [false, "list"], [false, "form"]],
            domain: [["stage_id", "=", stage.id]], target: "current",
        });
    }

    openRfmCategory(row) {
        const category = row.category === "none" ? false : row.category;
        this.action.doAction({
            type: "ir.actions.act_window", name: row.label,
            res_model: "res.partner", views: [[false, "list"], [false, "form"]],
            domain: category ? [["rfm_category", "=", category]] : [["rfm_category", "=", "none"]],
            target: "current",
        });
    }

    openCustomKpi(kpi) {
        if (!kpi || !kpi.model) return;
        this.action.doAction({
            type: "ir.actions.act_window", name: kpi.name,
            res_model: kpi.model, views: [[false, "list"], [false, "form"]],
            domain: kpi.domain || [], target: "current",
        });
    }
}

registry.category("actions").add(
    "chatroom_sales_intelligence.executive_dashboard", ExecutiveDashboard
);

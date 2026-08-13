/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onWillStart } from "@odoo/owl";

const KPI_STORAGE_KEY = "crm_customer_intelligence.rfm_dashboard_kpis";
const KPI_DEFAULTS = {
    customer_count: true,
    total_sales: true,
    average_ticket: true,
    average_score: true,
    at_risk_count: true,
    active_customer_count: false,
    invoice_count: false,
};

export class RfmDashboard extends Component {
    static template = "crm_customer_intelligence.RfmDashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            loading: true,
            period: "90",
            category: "all",
            source: "all",
            data: false,
            kpiConfigOpen: false,
            visibleKpis: this._loadVisibleKpis(),
        });
        onWillStart(() => this.loadData());
    }

    _loadVisibleKpis() {
        try {
            const saved = JSON.parse(localStorage.getItem(KPI_STORAGE_KEY) || "{}");
            return { ...KPI_DEFAULTS, ...saved };
        } catch {
            return { ...KPI_DEFAULTS };
        }
    }

    kpiOptions() {
        return [
            ["customer_count", "Clientes analizados"],
            ["total_sales", "Ventas del período"],
            ["average_ticket", "Ticket promedio"],
            ["average_score", "Score RFM promedio"],
            ["at_risk_count", "Clientes en riesgo"],
            ["active_customer_count", "Clientes activos"],
            ["invoice_count", "Facturas del período"],
        ];
    }

    toggleKpi(key) {
        const next = { ...this.state.visibleKpis, [key]: !this.state.visibleKpis[key] };
        if (!Object.values(next).some(Boolean)) {
            return;
        }
        this.state.visibleKpis = next;
        try {
            localStorage.setItem(KPI_STORAGE_KEY, JSON.stringify(next));
        } catch {
            // La configuración sigue activa durante la sesión.
        }
    }

    resetKpis() {
        this.state.visibleKpis = { ...KPI_DEFAULTS };
        try {
            localStorage.setItem(KPI_STORAGE_KEY, JSON.stringify(KPI_DEFAULTS));
        } catch {
            // La configuración sigue activa durante la sesión.
        }
    }

    async loadData() {
        this.state.loading = true;
        this.state.data = await this.orm.call(
            "res.partner", "get_rfm_dashboard_data",
            [this.state.period, this.state.category, false, this.state.source]
        );
        this.state.loading = false;
    }

    async changePeriod(ev) {
        this.state.period = ev.target.value;
        await this.loadData();
    }

    async changeCategory(ev) {
        this.state.category = ev.target.value;
        await this.loadData();
    }

    async changeSource(ev) {
        this.state.source = ev.target.value;
        await this.loadData();
    }

    async exportCsv() {
        const action = await this.orm.call(
            "res.partner", "action_export_rfm_dashboard_csv",
            [this.state.period, this.state.category, this.state.source]
        );
        await this.action.doAction(action);
    }

    async scheduleFollowups() {
        const action = await this.orm.call(
            "res.partner", "action_schedule_rfm_dashboard_followups",
            [this.state.period, this.state.category, this.state.source]
        );
        await this.action.doAction(action);
    }

    async refreshRfm() {
        this.state.loading = true;
        try {
            await this.orm.call("res.partner", "action_recompute_rfm_dashboard", []);
            await this.loadData();
        } finally {
            this.state.loading = false;
        }
    }

    formatMoney(value) {
        return (value || 0).toLocaleString(undefined, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    }

    formatVariation(value) {
        if (value === false || value === null || value === undefined) return "Sin período anterior";
        return `${value >= 0 ? "▲" : "▼"} ${Math.abs(value)}% frente al período anterior`;
    }

    categoryLabel(category) {
        const dynamic = (this.state.data?.category_options || []).find((item) => item.code === category);
        if (dynamic) return dynamic.label;
        return {
            a: "A - Alto valor",
            b: "B - Valor medio",
            c: "C - Bajo valor",
            none: "Sin historial",
        }[category] || category;
    }

    barWidth(value, rows, key) {
        const max = Math.max(...rows.map((row) => row[key] || 0), 1);
        return Math.max(5, Math.round(((value || 0) / max) * 100));
    }

    barHeight(value, rows, key) {
        const max = Math.max(...rows.map((row) => row[key] || 0), 1);
        return Math.max(value ? 6 : 0, Math.round(((value || 0) / max) * 100));
    }

    openSegments() {
        this.action.doAction({
            type: "ir.actions.act_window", name: "Segmentos RFM",
            res_model: "crm.rfm.segment", views: [[false, "list"], [false, "form"]],
            target: "current",
        });
    }

    openCampaigns() {
        this.action.doAction({
            type: "ir.actions.act_window", name: "Campañas WhatsApp",
            res_model: "chatroom.campaign", views: [[false, "list"], [false, "form"]],
            target: "current",
        });
    }

    openPartner(id) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "res.partner",
            res_id: id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openPartners(category = false) {
        const domain = category
            ? [["rfm_category", "=", category]]
            : [["rfm_category", "!=", "none"]];
        this.action.doAction({
            type: "ir.actions.act_window",
            name: category ? this.categoryLabel(category) : "Clientes RFM",
            res_model: "res.partner",
            views: [[false, "list"], [false, "form"]],
            domain,
            target: "current",
        });
    }

    openAtRisk() {
        const categories = (this.state.data?.category_options || [])
            .filter((item) => item.is_at_risk).map((item) => item.code);
        this.action.doAction({
            type: "ir.actions.act_window", name: "Clientes en riesgo",
            res_model: "res.partner", views: [[false, "list"], [false, "form"]],
            domain: categories.length ? [["rfm_category", "in", categories]] : [["rfm_category", "=", "c"]],
            target: "current",
        });
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

    openReportWizard() {
        this.action.doAction("crm_customer_intelligence.action_crm_rfm_dashboard_report_wizard");
    }
}

registry.category("actions").add(
    "crm_customer_intelligence.rfm_dashboard", RfmDashboard
);

/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onWillStart } from "@odoo/owl";

/**
 * "Mis pendientes de hoy": junta en una sola pantalla las conversaciones
 * de WhatsApp sin gestión reciente y las oportunidades estancadas del
 * usuario logueado, para que no tenga que ir recorriendo el kanban o el
 * pipeline registro por registro para saber a quién contactar primero.
 * Los datos se calculan en el servidor (chatroom.channel.
 * get_my_pending_followups) en una sola llamada.
 */
export class MyFollowupsDashboard extends Component {
    static template = "chatroom_sales_intelligence.MyFollowupsDashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        this.state = useState({
            loading: true,
            channels: [],
            leads: [],
        });

        onWillStart(() => this._loadData());
    }

    async _loadData() {
        this.state.loading = true;
        const data = await this.orm.call("chatroom.channel", "get_my_pending_followups", []);
        this.state.channels = data.channels;
        this.state.leads = data.leads;
        this.state.loading = false;
    }

    get isEmpty() {
        return !this.state.channels.length && !this.state.leads.length;
    }

    alertLabel(row) {
        return row.alert_state === "red" ? "Sin gestión hace" : "Sin gestión reciente";
    }

    openChannel(channelId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "chatroom.channel",
            res_id: channelId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openLead(leadId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "crm.lead",
            res_id: leadId,
            views: [[false, "form"]],
            target: "current",
        });
    }
}

registry.category("actions").add("chatroom_sales_intelligence.my_followups_dashboard", MyFollowupsDashboard);

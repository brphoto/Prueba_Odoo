/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { onWillUpdateProps, useState } from "@odoo/owl";
import { ContactPanel } from "@chatroom_whatsapp/chatroom_app/contact_panel";

patch(ContactPanel.prototype, {
    setup() {
        super.setup();
        this.aiAgent = useState({
            open: false,
            busy: false,
            task: false,
            error: "",
            canUse: null,
            metrics: { pending_count: 0, approval_count: 0, high_risk_count: 0, mode: "supervised" },
        });
        onWillUpdateProps((nextProps) => {
            if (nextProps.channelId !== this.props.channelId) {
                this.aiAgent.open = false;
                this.aiAgent.task = false;
                this.aiAgent.error = "";
                this.aiAgent.canUse = null;
                this.aiAgent.metrics = { pending_count: 0, approval_count: 0, high_risk_count: 0, mode: "supervised" };
            }
        });
    },

    async toggleAiAgent() {
        this.aiAgent.open = !this.aiAgent.open;
        if (this.aiAgent.open) {
            await this.loadAiAgent();
        }
    },

    onAiAgentHeaderKeydown(ev) {
        if (ev.key === "Enter" || ev.key === " ") {
            ev.preventDefault();
            this.toggleAiAgent();
        }
    },

    async loadAiAgent() {
        if (!this.props.channelId || this.aiAgent.busy) {
            return;
        }
        this.aiAgent.busy = true;
        this.aiAgent.error = "";
        try {
            const data = await this.orm.call(
                "chatroom.channel", "get_ai_agent_data", [this.props.channelId]);
            this.aiAgent.task = data?.task || false;
            this.aiAgent.canUse = data?.can_use !== false;
            this.aiAgent.metrics = data?.can_use === false ? this.aiAgent.metrics : {
                pending_count: data?.pending_count || 0,
                approval_count: data?.approval_count || 0,
                high_risk_count: data?.high_risk_count || 0,
                mode: data?.mode || "supervised",
            };
        } catch (error) {
            this.aiAgent.error = error.data ? error.data.message : error.message;
        } finally {
            this.aiAgent.busy = false;
        }
    },

    async createAiAgentTask() {
        if (!this.props.channelId || this.aiAgent.busy) {
            return;
        }
        this.aiAgent.busy = true;
        this.aiAgent.error = "";
        try {
            const action = await this.orm.call(
                "chatroom.channel", "action_ai_agent_create_task", [this.props.channelId]);
            await this.action.doAction(action, { onClose: () => this.loadAiAgent() });
            await this.loadAiAgent();
        } catch (error) {
            this.aiAgent.error = error.data ? error.data.message : error.message;
        } finally {
            this.aiAgent.busy = false;
        }
    },
});

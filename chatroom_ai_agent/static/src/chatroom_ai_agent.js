/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { onWillStart, onWillUpdateProps, useState } from "@odoo/owl";
import { user } from "@web/core/user";
import { ContactPanel } from "@chatroom_whatsapp/chatroom_app/contact_panel";

const EMPTY_METRICS = { pending_count: 0, approval_count: 0, high_risk_count: 0, mode: "supervised" };

// Preferencia del usuario ("auto", "open", "hidden"), leída una sola vez por
// sesión del navegador para no repetir la consulta en cada conversación.
let panelPrefPromise = null;

patch(ContactPanel.prototype, {
    setup() {
        super.setup();
        this.aiAgent = useState({
            open: false,
            busy: false,
            task: false,
            playbooks: [],
            choice: "router",
            route: false,
            commercialRouterEnabled: false,
            error: "",
            canUse: null,
            showHelp: false,
            panelPref: "auto",
            metrics: { ...EMPTY_METRICS },
        });
        onWillStart(async () => {
            if (!panelPrefPromise) {
                // Servicio sin proteger: la promesa se comparte entre paneles y
                // la de `useService` nunca se resuelve si este panel se destruye
                // antes de la respuesta, lo que dejaba colgados a los siguientes.
                panelPrefPromise = this.env.services.orm.read(
                    "res.users", [user.userId], ["chatroom_ai_agent_panel"])
                    .then((rows) => rows?.[0]?.chatroom_ai_agent_panel || "auto")
                    .catch(() => "auto");
            }
            this.aiAgent.panelPref = await panelPrefPromise;
            await this._autoLoadAiAgent(this.props.channelId);
        });
        onWillUpdateProps(async (nextProps) => {
            if (nextProps.channelId !== this.props.channelId) {
                Object.assign(this.aiAgent, {
                    open: false,
                    task: false,
                    playbooks: [],
                    choice: "router",
                    route: false,
                    commercialRouterEnabled: false,
                    error: "",
                    canUse: null,
                    showHelp: false,
                    metrics: { ...EMPTY_METRICS },
                });
                await this._autoLoadAiAgent(nextProps.channelId);
            }
        });
    },

    // Compacto: se abre solo si la conversación tiene algo por aprobar.
    async _autoLoadAiAgent(channelId) {
        if (!channelId || this.aiAgent.panelPref === "hidden") {
            return;
        }
        await this.loadAiAgent(channelId);
        if (this.aiAgent.panelPref === "open" || this.aiAgentNeedsApproval()) {
            this.aiAgent.open = true;
        }
    },

    aiAgentNeedsApproval() {
        return this.aiAgent.task?.state === "awaiting_approval";
    },

    aiAgentModeLabel() {
        return { supervised: "supervisado", automatic: "automático", disabled: "desactivado" }[
            this.aiAgent.metrics.mode] || this.aiAgent.metrics.mode;
    },

    aiAgentChoices() {
        const choices = [];
        if (this.aiAgent.route) {
            choices.push({ value: "router", label: `Atención sugerida: ${this.aiAgent.route.label}` });
        }
        choices.push({ value: "plan", label: "Plan completo de la conversación" });
        for (const playbook of this.aiAgent.playbooks) {
            choices.push({ value: `playbook:${playbook.id}`, label: playbook.name });
        }
        return choices;
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

    async loadAiAgent(channelId = this.props.channelId) {
        if (!channelId) {
            return;
        }
        // La última conversación pedida manda: si el usuario cambia de chat
        // mientras llega la respuesta anterior, esa respuesta se descarta.
        this._aiAgentLoadingFor = channelId;
        this.aiAgent.error = "";
        try {
            const data = await this.orm.call("chatroom.channel", "get_ai_agent_data", [channelId]);
            if (this._aiAgentLoadingFor !== channelId) {
                return;
            }
            this.aiAgent.task = data?.task || false;
            this.aiAgent.playbooks = data?.playbooks || [];
            this.aiAgent.route = data?.route || false;
            this.aiAgent.commercialRouterEnabled = data?.commercial_router_enabled === true;
            this.aiAgent.canUse = data?.can_use !== false;
            if (data?.panel_pref) {
                this.aiAgent.panelPref = data.panel_pref;
            }
            const values = this.aiAgentChoices().map((choice) => choice.value);
            if (!values.includes(this.aiAgent.choice)) {
                this.aiAgent.choice = values[0];
            }
            this.aiAgent.metrics = data?.can_use === false ? this.aiAgent.metrics : {
                pending_count: data?.pending_count || 0,
                approval_count: data?.approval_count || 0,
                high_risk_count: data?.high_risk_count || 0,
                mode: data?.mode || "supervised",
            };
        } catch (error) {
            if (this._aiAgentLoadingFor === channelId) {
                this.aiAgent.error = error.data ? error.data.message : error.message;
            }
        }
    },

    async _runAiAgentCall(method, args = []) {
        if (!this.props.channelId || this.aiAgent.busy) {
            return;
        }
        this.aiAgent.busy = true;
        this.aiAgent.error = "";
        let action = false;
        try {
            action = await this.orm.call("chatroom.channel", method, [this.props.channelId, ...args]);
        } catch (error) {
            this.aiAgent.error = error.data ? error.data.message : error.message;
        } finally {
            this.aiAgent.busy = false;
        }
        if (action) {
            await this.action.doAction(action, { onClose: () => this.loadAiAgent() });
            await this.loadAiAgent();
        }
    },

    async runAiAgentChoice() {
        const choice = this.aiAgent.choice || "plan";
        if (choice === "router") {
            return this.runCommercialRouter();
        }
        if (choice.startsWith("playbook:")) {
            return this._runAiAgentCall("action_ai_agent_apply_playbook", [Number(choice.split(":")[1])]);
        }
        return this.createAiAgentTask();
    },

    async createAiAgentTask() {
        return this._runAiAgentCall("action_ai_agent_create_task");
    },

    async runCommercialRouter() {
        return this._runAiAgentCall("action_ai_agent_commercial_router");
    },

    async applyAiPlaybook() {
        const choice = this.aiAgent.choice || "";
        if (choice.startsWith("playbook:")) {
            return this._runAiAgentCall("action_ai_agent_apply_playbook", [Number(choice.split(":")[1])]);
        }
    },

    async openAiAgentTask() {
        if (this.aiAgent.task?.id) {
            return this._runAiAgentCall("action_ai_agent_open_task", [this.aiAgent.task.id]);
        }
    },

    openAiAgentQueue() {
        this.action.doAction("chatroom_ai_agent.action_chatroom_ai_approvals");
    },

    async hideAiAgentPanel() {
        await this.orm.call("res.users", "set_chatroom_ai_agent_panel", ["hidden"]);
        panelPrefPromise = Promise.resolve("hidden");
        this.aiAgent.panelPref = "hidden";
        this.notification.add(
            "Panel del Agente IA oculto. Puedes volver a mostrarlo en Mis preferencias > Chatroom.",
            { type: "info" });
    },
});

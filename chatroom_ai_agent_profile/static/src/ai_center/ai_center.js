/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const TABS = [
    { key: "today", label: "Hoy", icon: "fa-inbox" },
    { key: "setup", label: "Configurar", icon: "fa-sliders" },
    { key: "improve", label: "Mejorar", icon: "fa-graduation-cap" },
    { key: "results", label: "Resultados", icon: "fa-line-chart" },
];
const TAB_STORAGE_KEY = "chatroom_ai_agent_profile.ai_center_tab";

function readTab() {
    try {
        const tab = window.localStorage.getItem(TAB_STORAGE_KEY);
        return TABS.some((item) => item.key === tab) ? tab : "today";
    } catch {
        return "today";
    }
}

// Todo el agente en una pantalla: lo que hay que hacer hoy, cómo está
// configurado, qué le falta aprender y cómo le va.
export class AiCenter extends Component {
    static template = "chatroom_ai_agent_profile.AiCenter";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.tabs = TABS;
        this.state = useState({
            loading: true,
            tab: readTab(),
            data: false,
            drafts: {},
            answers: {},
            busy: false,
            knowledgeTitle: "",
            knowledgeText: "",
            template: "",
            question: "",
            answer: "",
            asking: false,
        });
        onWillStart(() => this.load());
    }

    async load() {
        const data = await this.orm.call("chatroom.ai.agent.profile", "get_ai_center_data", []);
        this.state.data = data;
        this.state.template = data.profile.business_template || "";
        for (const item of data.today.pending) {
            if (!(item.id in this.state.drafts)) {
                this.state.drafts[item.id] = item.text;
            }
        }
        for (const gap of data.today.gaps) {
            if (!(gap.id in this.state.answers)) {
                this.state.answers[gap.id] = gap.answer;
            }
        }
        this.state.loading = false;
    }

    get profileId() {
        return this.state.data.profile.id;
    }

    get modeLabel() {
        const profile = this.state.data.profile;
        const mode = profile.modes.find((item) => item.key === profile.autonomy_mode);
        return mode ? mode.label : "";
    }

    get todayCount() {
        const today = this.state.data.today;
        return today.pending_count + today.handoffs.length;
    }

    selectTab(key) {
        this.state.tab = key;
        try {
            window.localStorage.setItem(TAB_STORAGE_KEY, key);
        } catch {
            // solo es una comodidad
        }
    }

    async run(callback, message) {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            await callback();
            if (message) {
                this.notification.add(message, { type: "success" });
            }
            await this.load();
        } catch (error) {
            this.notification.add(error.data?.message || error.message, { type: "danger" });
        } finally {
            this.state.busy = false;
        }
    }

    // --- Hoy ---------------------------------------------------------
    sendDraft(item) {
        const text = (this.state.drafts[item.id] || "").trim();
        return this.run(async () => {
            if (text && text !== item.text) {
                await this.orm.write("chatroom.ai.suggestion", [item.id], { suggested_text: text });
            }
            await this.orm.call("chatroom.ai.suggestion", "action_approve_and_send", [[item.id]]);
            delete this.state.drafts[item.id];
        }, text !== item.text ? "Enviado. La IA aprendió tu corrección." : "Enviado.");
    }

    discardDraft(item) {
        return this.run(async () => {
            await this.orm.call("chatroom.ai.suggestion", "action_discard", [[item.id]]);
            delete this.state.drafts[item.id];
        }, "Borrador descartado.");
    }

    openChat(channelId) {
        this.action.doAction({
            type: "ir.actions.client",
            tag: "chatroom_whatsapp.chatroom_app",
            name: "Chatroom",
            params: { channel_id: channelId },
        });
    }

    takeOver(item) {
        return this.run(async () => {
            await this.orm.call("chatroom.channel", "action_ai_take_over", [[item.id]]);
            this.openChat(item.id);
        });
    }

    // --- Configurar --------------------------------------------------
    setMode(mode) {
        if (mode === this.state.data.profile.autonomy_mode) {
            return;
        }
        return this.run(
            () => this.orm.call("chatroom.ai.agent.profile", "action_set_autonomy_mode", [[this.profileId], mode]),
            "Autonomía actualizada.");
    }

    applyTemplate() {
        if (!this.state.template) {
            return;
        }
        return this.run(
            () => this.orm.call("chatroom.ai.agent.profile", "action_apply_template",
                [[this.profileId], this.state.template]),
            "Plantilla aplicada: revisa los guiones y completa la información sugerida.");
    }

    publishKnowledge() {
        const text = this.state.knowledgeText.trim();
        if (!text) {
            this.notification.add("Escribe la información que quieres que la IA use.", { type: "warning" });
            return;
        }
        return this.run(async () => {
            await this.orm.call("chatroom.ai.agent.profile", "action_quick_knowledge",
                [[this.profileId], this.state.knowledgeTitle, text]);
            this.state.knowledgeTitle = "";
            this.state.knowledgeText = "";
        }, "Publicado: la IA ya lo usa desde el próximo mensaje.");
    }

    toggleAutoReply() {
        const method = this.state.data.profile.auto_reply_on ? "action_disable_auto_reply" : "action_enable_auto_reply";
        return this.run(() => this.orm.call("chatroom.ai.agent.profile", method, [[this.profileId]]));
    }

    openAction(xmlId, options = {}) {
        this.action.doAction(xmlId, { onClose: () => this.load(), ...options });
    }

    async openProfileAction(method) {
        const action = await this.orm.call("chatroom.ai.agent.profile", method, [[this.profileId]]);
        if (action && typeof action === "object") {
            this.action.doAction(action, { onClose: () => this.load() });
        } else {
            await this.load();
        }
    }

    openProfile() {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "chatroom.ai.agent.profile",
            res_id: this.profileId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    // --- Mejorar -----------------------------------------------------
    publishGap(gap) {
        const answer = (this.state.answers[gap.id] || "").trim();
        if (!answer) {
            this.notification.add("Escribe la respuesta antes de publicarla.", { type: "warning" });
            return;
        }
        return this.run(async () => {
            await this.orm.write("chatroom.ai.knowledge.gap", [gap.id], { answer });
            await this.orm.call("chatroom.ai.knowledge.gap", "action_publish", [[gap.id]]);
        }, "Publicado: la próxima vez la IA lo responde sola.");
    }

    ignoreGap(gap) {
        return this.run(() => this.orm.call("chatroom.ai.knowledge.gap", "action_ignore", [[gap.id]]));
    }

    // --- Resultados --------------------------------------------------
    async ask(question) {
        const text = (question ?? this.state.question).trim();
        if (!text || this.state.asking) {
            return;
        }
        this.state.question = text;
        this.state.asking = true;
        this.state.answer = "";
        try {
            this.state.answer = await this.orm.call("chatroom.ai.agent.profile", "ask_insights",
                [[this.profileId], text]);
        } catch (error) {
            this.notification.add(error.data?.message || error.message, { type: "danger" });
        } finally {
            this.state.asking = false;
        }
    }

    onAskKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            this.ask();
        }
    }

    get suggestedQuestions() {
        return [
            "¿Qué preguntan más los clientes?",
            "¿Por qué pasan conversaciones a una persona?",
            "¿Qué información me falta cargar?",
        ];
    }

    trendHeight(week) {
        const max = Math.max(1, ...this.state.data.results.trend.map((item) => item.total));
        return `${Math.max(4, Math.round((week.total / max) * 100))}%`;
    }

    formatMoney(value) {
        return `$${(value || 0).toFixed(4)}`;
    }
}

registry.category("actions").add("chatroom_ai_agent_profile.ai_center", AiCenter);

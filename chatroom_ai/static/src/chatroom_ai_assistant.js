/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { onMounted, onWillUnmount, onWillUpdateProps, useState } from "@odoo/owl";
import { ContactPanel } from "@chatroom_whatsapp/chatroom_app/contact_panel";

patch(ContactPanel.prototype, {
    setup() {
        super.setup();
        this.aiAssistant = useState({
            open: false,
            loading: false,
            busy: false,
            providerReady: false,
            approvalRequired: true,
            summary: "",
            intent: "",
            quickActions: [],
            actionId: false,
            canConfigure: false,
            showDetails: false,
            modelId: false,
            modelOptions: [],
            knowledgeCount: 0,
            usage: { requests: 0, tokens: 0, last_model: "" },
            safetyPolicy: { enabled: true, min_confidence: 0.80, cooldown_minutes: 15, daily_limit: 30, escalate_negative: true },
            budget: false,
            aiPaused: false,
            suggestion: false,
            error: "",
        });
        onWillUpdateProps((nextProps) => {
            if (nextProps.channelId !== this.props.channelId) {
                this._resetAiAssistant();
            }
        });
        // El compositor (✨ o /atajo) avisa cuando cambió algo que el panel
        // muestra: borrador, resumen o intención.
        this._onAiAssistantRefresh = (ev) => {
            if ((ev.detail || {}).channelId === this.props.channelId && this.aiAssistant.open) {
                this._loadAiAssistant();
            }
        };
        onMounted(() => window.addEventListener("chatroom-ai-assistant-refresh", this._onAiAssistantRefresh));
        onWillUnmount(() => window.removeEventListener("chatroom-ai-assistant-refresh", this._onAiAssistantRefresh));
    },

    _resetAiAssistant() {
        this.aiAssistant.open = false;
        this.aiAssistant.loading = false;
        this.aiAssistant.busy = false;
        this.aiAssistant.summary = "";
        this.aiAssistant.intent = "";
        this.aiAssistant.quickActions = [];
        this.aiAssistant.actionId = false;
        this.aiAssistant.showDetails = false;
        this.aiAssistant.modelId = false;
        this.aiAssistant.modelOptions = [];
        this.aiAssistant.suggestion = false;
        this.aiAssistant.usage = { requests: 0, tokens: 0, last_model: "" };
        this.aiAssistant.safetyPolicy = { enabled: true, min_confidence: 0.80, cooldown_minutes: 15, daily_limit: 30, escalate_negative: true };
        this.aiAssistant.budget = false;
        this.aiAssistant.aiPaused = false;
        this.aiAssistant.error = "";
    },

    async _loadAiAssistant() {
        if (!this.props.channelId) {
            return;
        }
        this.aiAssistant.loading = true;
        this.aiAssistant.error = "";
        try {
            const data = await this.orm.call(
                "chatroom.channel", "get_ai_assistant_data", [this.props.channelId]);
            this._applyAiAssistantData(data);
        } catch (error) {
            this.aiAssistant.error = error.data ? error.data.message : error.message;
        } finally {
            this.aiAssistant.loading = false;
        }
    },

    _applyAiAssistantData(data) {
        this.aiAssistant.providerReady = Boolean(data?.provider_ready);
        this.aiAssistant.approvalRequired = data?.approval_required !== false;
        this.aiAssistant.summary = data?.summary || "";
        this.aiAssistant.intent = data?.intent || "";
        this.aiAssistant.knowledgeCount = data?.knowledge_count || 0;
        this.aiAssistant.usage = data?.usage || { requests: 0, tokens: 0, last_model: "" };
        this.aiAssistant.modelOptions = data?.model_options || [];
        this.aiAssistant.modelId = data?.selected_model_id || this.aiAssistant.modelId || false;
        this.aiAssistant.safetyPolicy = data?.safety_policy || this.aiAssistant.safetyPolicy;
        this.aiAssistant.budget = data?.budget || false;
        this.aiAssistant.aiPaused = Boolean(data?.ai_paused);
        this.aiAssistant.suggestion = data?.suggestion || false;
        this.aiAssistant.quickActions = data?.quick_actions || [];
        this.aiAssistant.canConfigure = Boolean(data?.can_configure);
        const ids = this.aiAssistant.quickActions.map((action) => action.id);
        if (!ids.includes(this.aiAssistant.actionId)) {
            this.aiAssistant.actionId = ids[0] || false;
        }
    },

    selectedAiAction() {
        return this.aiAssistant.quickActions.find(
            (action) => action.id === this.aiAssistant.actionId) || false;
    },

    toggleAiDetails() {
        this.aiAssistant.showDetails = !this.aiAssistant.showDetails;
    },

    openAiQuickActionConfig() {
        this.action.doAction("chatroom_ai.action_chatroom_ai_quick_action");
    },

    async toggleAiAssistant() {
        this.aiAssistant.open = !this.aiAssistant.open;
        if (this.aiAssistant.open && !this.aiAssistant.providerReady && !this.aiAssistant.error) {
            await this._loadAiAssistant();
        }
    },

    onAiAssistantHeaderKeydown(ev) {
        if (ev.key === "Enter" || ev.key === " ") {
            ev.preventDefault();
            this.toggleAiAssistant();
        }
    },

    onAiActionChange(ev) {
        this.aiAssistant.actionId = ev.target.value ? Number(ev.target.value) : false;
    },

    onAiModelChange(ev) {
        this.aiAssistant.modelId = ev.target.value ? Number(ev.target.value) : false;
    },

    async runAiAction() {
        const action = this.selectedAiAction();
        if (!action || !this.props.channelId || this.aiAssistant.busy) {
            return;
        }
        if (action.output_mode === "rewrite") {
            // Reescribir trabaja sobre lo escrito en el mensaje: lo ejecuta
            // el compositor, que es quien tiene el borrador.
            window.dispatchEvent(new CustomEvent("chatroom-ai-run-quick-action", {
                detail: { channelId: this.props.channelId, action },
            }));
            return;
        }
        this.aiAssistant.busy = true;
        this.aiAssistant.error = "";
        try {
            const result = await this.orm.call(
                "chatroom.channel", "action_ai_run_quick_action",
                [this.props.channelId, action.id], {
                    model_id: this.aiAssistant.modelId || false,
                }) || {};
            if (result.mode === "reply") {
                // Un resumen es material interno: nunca debe convivir con la
                // tarjeta de respuesta ni parecer texto listo para enviar.
                this.aiAssistant.summary = "";
                this.aiAssistant.suggestion = result.suggestion || false;
            } else if (result.mode === "summary") {
                this.aiAssistant.suggestion = false;
                this.aiAssistant.summary = result.summary || "";
            } else if (result.mode === "intent") {
                this.aiAssistant.intent = result.intent || "otro";
                this.notification.add(`Intención: ${this.aiAssistant.intent}`, { type: "success" });
            } else if (result.mode === "note") {
                window.dispatchEvent(new CustomEvent("chatroom-ai-reload-messages", {
                    detail: { channelId: this.props.channelId },
                }));
                this.notification.add("Nota interna guardada en la conversación.", { type: "success" });
            } else if (["agent_task", "action"].includes(result.mode) && result.action) {
                await this.action.doAction(result.action);
            }
        } catch (error) {
            this.aiAssistant.error = error.data ? error.data.message : error.message;
        } finally {
            this.aiAssistant.busy = false;
        }
    },

    suggestionStateLabel() {
        const labels = {
            draft: "borrador",
            approved: "aprobada",
            sent: "enviada",
            rejected: "rechazada",
            error: "error",
        };
        return labels[this.aiAssistant.suggestion?.state] || "";
    },

    safetyConfidenceLabel() {
        return `${Math.round((this.aiAssistant.safetyPolicy?.min_confidence || 0) * 100)}%`;
    },

    suggestionConfidenceLabel() {
        const confidence = Number(this.aiAssistant.suggestion?.confidence || 0);
        return `${Math.round(Math.max(0, Math.min(1, confidence)) * 100)}%`;
    },

    suggestionSourceLabel() {
        const source = this.aiAssistant.suggestion?.source;
        const label = source === "conversation" ? "Conversación" : source === "manual" ? "Generación manual" : "No indicada";
        return this.aiAssistant.suggestion?.quick_action
            ? `${this.aiAssistant.suggestion.quick_action} · ${label}` : label;
    },

    budgetLabel() {
        const budget = this.aiAssistant.budget;
        if (!budget) {
            return "";
        }
        if (budget.state === "no_limit") {
            return "Sin limite configurado";
        }
        const remaining = Number(budget.remaining || 0).toFixed(2);
        return `${remaining} ${(budget.currency || "usd").toUpperCase()} referencial`;
    },

    useAiSuggestion() {
        const suggestion = this.aiAssistant.suggestion;
        if (!suggestion?.text || !this.props.channelId) {
            return;
        }
        window.dispatchEvent(new CustomEvent("chatroom-ai-use-response", {
            detail: { channelId: this.props.channelId, text: suggestion.text },
        }));
        this.notification.add("Respuesta colocada en el compositor para revisarla.", {
            type: "success",
        });
    },

    async _runAiAssistant(callName, onResult) {
        if (!this.props.channelId || this.aiAssistant.busy) {
            return;
        }
        this.aiAssistant.busy = true;
        this.aiAssistant.error = "";
        try {
            const result = await this.orm.call(
                "chatroom.channel", callName, [this.props.channelId], {
                    model_id: this.aiAssistant.modelId || false,
                });
            onResult(result);
        } catch (error) {
            this.aiAssistant.error = error.data ? error.data.message : error.message;
        } finally {
            this.aiAssistant.busy = false;
        }
    },

    async prepareAiSuggestion() {
        this.aiAssistant.summary = "";
        await this._runAiAssistant("action_ai_prepare_suggestion", (suggestion) => {
            this.aiAssistant.suggestion = suggestion;
        });
    },

    async prepareAiSummary() {
        this.aiAssistant.suggestion = false;
        await this._runAiAssistant("action_ai_prepare_summary", (summary) => {
            this.aiAssistant.summary = summary || "";
        });
    },

    async classifyAiIntent() {
        this.aiAssistant.summary = "";
        this.aiAssistant.suggestion = false;
        await this._runAiAssistant("action_ai_classify_intent", (intent) => {
            this.aiAssistant.intent = intent || "otro";
        });
    },

    async approveAiSuggestion() {
        const id = this.aiAssistant.suggestion?.id;
        if (!id || this.aiAssistant.busy) {
            return;
        }
        this.aiAssistant.busy = true;
        try {
            const data = await this.orm.call(
                "chatroom.channel", "action_ai_approve_suggestion",
                [this.props.channelId, id]);
            this._applyAiAssistantData(data);
        } catch (error) {
            this.aiAssistant.error = error.data ? error.data.message : error.message;
        } finally {
            this.aiAssistant.busy = false;
        }
    },

    async saveAiSuggestion() {
        const suggestion = this.aiAssistant.suggestion;
        if (!suggestion?.id || this.aiAssistant.busy) {
            return;
        }
        this.aiAssistant.busy = true;
        try {
            const data = await this.orm.call(
                "chatroom.channel", "action_ai_update_suggestion",
                [this.props.channelId, suggestion.id, suggestion.text]);
            this._applyAiAssistantData(data);
            this.notification.add("Cambios guardados en el borrador.", { type: "success" });
        } catch (error) {
            this.aiAssistant.error = error.data ? error.data.message : error.message;
        } finally {
            this.aiAssistant.busy = false;
        }
    },

    async discardAiSuggestion() {
        const id = this.aiAssistant.suggestion?.id;
        if (!id || this.aiAssistant.busy) {
            return;
        }
        this.aiAssistant.busy = true;
        try {
            const data = await this.orm.call(
                "chatroom.channel", "action_ai_discard_suggestion",
                [this.props.channelId, id]);
            this._applyAiAssistantData(data);
        } catch (error) {
            this.aiAssistant.error = error.data ? error.data.message : error.message;
        } finally {
            this.aiAssistant.busy = false;
        }
    },

    async sendAiSuggestion() {
        const id = this.aiAssistant.suggestion?.id;
        if (!id || this.aiAssistant.busy) {
            return;
        }
        this.aiAssistant.busy = true;
        try {
            const data = await this.orm.call(
                "chatroom.channel", "action_ai_send_suggestion",
                [this.props.channelId, id]);
            this._applyAiAssistantData(data);
            this.notification.add("Respuesta enviada al cliente.", { type: "success" });
        } catch (error) {
            this.aiAssistant.error = error.data ? error.data.message : error.message;
        } finally {
            this.aiAssistant.busy = false;
        }
    },

    async rateAiSuggestion(feedbackState) {
        const id = this.aiAssistant.suggestion?.id;
        if (!id || this.aiAssistant.busy) {
            return;
        }
        this.aiAssistant.busy = true;
        try {
            const data = await this.orm.call(
                "chatroom.channel", "action_ai_feedback_suggestion",
                [this.props.channelId, id, feedbackState]);
            this._applyAiAssistantData(data);
            this.notification.add("Evaluación guardada para las métricas de calidad.", { type: "success" });
        } catch (error) {
            this.aiAssistant.error = error.data ? error.data.message : error.message;
        } finally {
            this.aiAssistant.busy = false;
        }
    },

    rateAiHelpful() {
        return this.rateAiSuggestion("helpful");
    },

    rateAiEdited() {
        return this.rateAiSuggestion("edited");
    },

    rateAiUnsafe() {
        return this.rateAiSuggestion("unsafe");
    },
});

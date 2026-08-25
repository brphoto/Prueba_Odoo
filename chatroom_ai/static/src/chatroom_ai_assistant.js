/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { onWillUpdateProps, useState } from "@odoo/owl";
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
            mode: "suggestion",
            knowledgeCount: 0,
            usage: { requests: 0, tokens: 0, last_model: "" },
            suggestion: false,
            error: "",
        });
        onWillUpdateProps((nextProps) => {
            if (nextProps.channelId !== this.props.channelId) {
                this._resetAiAssistant();
            }
        });
    },

    _resetAiAssistant() {
        this.aiAssistant.open = false;
        this.aiAssistant.loading = false;
        this.aiAssistant.busy = false;
        this.aiAssistant.summary = "";
        this.aiAssistant.intent = "";
        this.aiAssistant.mode = "suggestion";
        this.aiAssistant.suggestion = false;
        this.aiAssistant.usage = { requests: 0, tokens: 0, last_model: "" };
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
        this.aiAssistant.suggestion = data?.suggestion || false;
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

    onAiModeChange(ev) {
        this.aiAssistant.mode = ev.target.value;
    },

    async runAiAction() {
        if (this.aiAssistant.mode === "summary") {
            return this.prepareAiSummary();
        }
        if (this.aiAssistant.mode === "intent") {
            return this.classifyAiIntent();
        }
        return this.prepareAiSuggestion();
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
                "chatroom.channel", callName, [this.props.channelId]);
            onResult(result);
        } catch (error) {
            this.aiAssistant.error = error.data ? error.data.message : error.message;
        } finally {
            this.aiAssistant.busy = false;
        }
    },

    async prepareAiSuggestion() {
        await this._runAiAssistant("action_ai_prepare_suggestion", (suggestion) => {
            this.aiAssistant.suggestion = suggestion;
        });
    },

    async prepareAiSummary() {
        await this._runAiAssistant("action_ai_prepare_summary", (summary) => {
            this.aiAssistant.summary = summary || "";
        });
    },

    async classifyAiIntent() {
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
});

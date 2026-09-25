/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { onMounted, onWillUnmount, useState } from "@odoo/owl";
import { ChatroomThreadCore } from "@chatroom_whatsapp/chatroom_thread/chatroom_thread_core";

// "/atajo" al final del texto: lo que va antes es el borrador (para las
// acciones que reescriben lo escrito, como /mejorar o /traducir).
const SLASH_RE = /(^|\s)\/([\w-]*)$/;

/**
 * IA dentro del compositor: botón ✨ con las acciones de IA de la
 * conversación y atajos "/precio", "/mejorar"... escritos en el mensaje.
 * Todo pasa por chatroom.channel.action_ai_run_quick_action: nada se envía
 * al cliente sin que el agente pulse enviar.
 */
patch(ChatroomThreadCore.prototype, {
    setup() {
        super.setup();
        this.aiQuick = useState({
            menuOpen: false,
            slashOpen: false,
            filter: "",
            index: 0,
            actions: [],
            loadedFor: false,
            busy: false,
        });
        this._onAiRunQuickAction = this._onAiRunQuickAction.bind(this);
        this._onAiReloadMessages = this._onAiReloadMessages.bind(this);
        onMounted(() => {
            window.addEventListener("chatroom-ai-run-quick-action", this._onAiRunQuickAction);
            window.addEventListener("chatroom-ai-reload-messages", this._onAiReloadMessages);
        });
        onWillUnmount(() => {
            window.removeEventListener("chatroom-ai-run-quick-action", this._onAiRunQuickAction);
            window.removeEventListener("chatroom-ai-reload-messages", this._onAiReloadMessages);
        });
    },

    // ------------------------------------------------------------------
    // Carga de acciones
    // ------------------------------------------------------------------
    async _loadAiQuickActions() {
        const channelId = this.channelId;
        if (!channelId || this.aiQuick.loadedFor === channelId) {
            return this.aiQuick.actions;
        }
        try {
            this.aiQuick.actions = await this.orm.call(
                "chatroom.channel", "get_ai_quick_actions", [channelId]) || [];
        } catch {
            this.aiQuick.actions = [];
        }
        this.aiQuick.loadedFor = channelId;
        return this.aiQuick.actions;
    },

    aiQuickVisibleActions() {
        const filter = (this.aiQuick.filter || "").toLowerCase();
        if (!filter) {
            return this.aiQuick.actions;
        }
        return this.aiQuick.actions.filter((action) =>
            (action.shortcut || "").toLowerCase().startsWith(filter)
            || (action.name || "").toLowerCase().includes(filter));
    },

    aiQuickModeLabel(action) {
        return {
            reply: "Borrador",
            rewrite: "Reescribe",
            note: "Nota interna",
            summary: "Resumen",
            intent: "Intención",
            agent_task: "Agente",
            insurance_profile: "Perfil",
            insurance_compare: "Comparativo",
        }[action.output_mode] || "";
    },

    // ------------------------------------------------------------------
    // Botón ✨
    // ------------------------------------------------------------------
    async toggleAiQuickMenu() {
        if (this.aiQuick.menuOpen) {
            this.aiQuick.menuOpen = false;
            return;
        }
        this.state.cannedOpen = false;
        this.state.quickButtonsOpen = false;
        this.aiQuick.slashOpen = false;
        this.aiQuick.filter = "";
        this.aiQuick.index = 0;
        await this._loadAiQuickActions();
        this.aiQuick.menuOpen = true;
    },

    closeAiQuickMenus() {
        this.aiQuick.menuOpen = false;
        this.aiQuick.slashOpen = false;
        this.aiQuick.filter = "";
        this.aiQuick.index = 0;
    },

    // ------------------------------------------------------------------
    // Atajos "/"
    // ------------------------------------------------------------------
    onComposerInput(ev) {
        const result = super.onComposerInput ? super.onComposerInput(ev) : undefined;
        if (!this.state.aiAvailable || this.state.noteMode) {
            return result;
        }
        const match = SLASH_RE.exec(this.state.composerText || "");
        if (match) {
            this.aiQuick.filter = match[2] || "";
            this.aiQuick.index = 0;
            this.aiQuick.menuOpen = false;
            this.aiQuick.slashOpen = true;
            this._loadAiQuickActions();
        } else if (this.aiQuick.slashOpen) {
            this.closeAiQuickMenus();
        }
        return result;
    },

    onComposerKeydown(ev) {
        const open = this.aiQuick.slashOpen || this.aiQuick.menuOpen;
        const actions = open ? this.aiQuickVisibleActions() : [];
        if (open && actions.length) {
            if (ev.key === "ArrowDown") {
                ev.preventDefault();
                this.aiQuick.index = (this.aiQuick.index + 1) % actions.length;
                return;
            }
            if (ev.key === "ArrowUp") {
                ev.preventDefault();
                this.aiQuick.index = (this.aiQuick.index - 1 + actions.length) % actions.length;
                return;
            }
            if (ev.key === "Enter" || ev.key === "Tab") {
                ev.preventDefault();
                this.chooseAiQuickAction(actions[Math.min(this.aiQuick.index, actions.length - 1)]);
                return;
            }
        }
        if (open && ev.key === "Escape") {
            ev.preventDefault();
            this.closeAiQuickMenus();
            return;
        }
        return super.onComposerKeydown(ev);
    },

    async chooseAiQuickAction(action) {
        if (!action) {
            return;
        }
        let draft = this.state.composerText || "";
        if (this.aiQuick.slashOpen) {
            // Se quita el "/atajo" del texto: lo anterior es el borrador.
            draft = draft.replace(SLASH_RE, "$1").trimEnd();
            this.state.composerText = draft;
        }
        this.closeAiQuickMenus();
        await this.runAiQuickAction(action, draft);
    },

    // ------------------------------------------------------------------
    // Ejecución
    // ------------------------------------------------------------------
    async runAiQuickAction(action, draft) {
        if (!this.channelId || this.aiQuick.busy) {
            return;
        }
        this.aiQuick.busy = true;
        try {
            const result = await this.orm.call(
                "chatroom.channel", "action_ai_run_quick_action",
                [this.channelId, action.id], { draft_text: draft || false });
            await this._applyAiQuickResult(action, result || {});
        } catch (error) {
            this.notification.add(error.data ? error.data.message : error.message, {
                type: "danger", title: action.name,
            });
        } finally {
            this.aiQuick.busy = false;
        }
    },

    async _applyAiQuickResult(action, result) {
        const refreshPanel = () => window.dispatchEvent(new CustomEvent(
            "chatroom-ai-assistant-refresh", { detail: { channelId: this.channelId } }));
        switch (result.mode) {
            case "reply":
                this.state.noteMode = false;
                this.state.composerText = result.suggestion?.text || "";
                this.notification.add(
                    "Borrador de IA en el mensaje. Revísalo antes de enviar.", { type: "info" });
                refreshPanel();
                break;
            case "rewrite":
                this.state.noteMode = false;
                this.state.composerText = result.text || this.state.composerText;
                break;
            case "note":
                await this._loadMessages();
                this.notification.add("Nota interna guardada en la conversación.", { type: "success" });
                break;
            case "summary":
                this.notification.add(result.summary || "", {
                    type: "info", title: "Resumen de la conversación", sticky: true,
                });
                refreshPanel();
                break;
            case "intent":
                this.notification.add(`Intención: ${result.intent || "otro"}`, { type: "success" });
                refreshPanel();
                break;
            case "agent_task":
            case "action":
                // Abre lo que preparó la acción (tarea del agente, comparativo...).
                if (result.action) {
                    await this.action.doAction(result.action, { onClose: refreshPanel });
                }
                refreshPanel();
                break;
        }
    },

    // Acciones lanzadas desde el panel lateral que necesitan el borrador
    // del compositor (reescribir / traducir).
    async _onAiRunQuickAction(ev) {
        const detail = ev.detail || {};
        if (detail.channelId !== this.channelId || !detail.action) {
            return;
        }
        await this.runAiQuickAction(detail.action, this.state.composerText || "");
    },

    async _onAiReloadMessages(ev) {
        if ((ev.detail || {}).channelId === this.channelId) {
            await this._loadMessages();
        }
    },
});

/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ChatroomThreadCore } from "@chatroom_whatsapp/chatroom_thread/chatroom_thread_core";

// El borrador de la IA aparece escrito en el cuadro del chat: Enter lo envía,
// y si la persona lo corrige antes de enviar, la IA aprende la corrección.
patch(ChatroomThreadCore.prototype, {
    setup() {
        super.setup(...arguments);
        this.state.aiDraft = false;
    },

    async _loadChannel(channelId = this.channelId) {
        const result = await super._loadChannel(...arguments);
        await this._loadAiDraft(channelId);
        return result;
    },

    async _loadAiDraft(channelId) {
        if (!channelId) {
            return;
        }
        let draft = false;
        try {
            draft = await this.orm.call("chatroom.channel", "get_ai_pending_draft", [channelId]);
        } catch {
            draft = false; // sin permiso o sin IA: el chat funciona igual
        }
        if (channelId !== this._composerChannelId) {
            return; // ya se cambió de conversación
        }
        const previous = this.state.aiDraft;
        this.state.aiDraft = draft || false;
        if (!draft) {
            if (previous && this.state.composerText === previous.text) {
                this.state.composerText = "";
            }
            return;
        }
        const current = (this.state.composerText || "").trim();
        if (!current || (previous && current === previous.text)) {
            this.state.composerText = draft.text;
        }
    },

    get aiDraftInComposer() {
        const draft = this.state.aiDraft;
        return Boolean(draft && !this.state.noteMode);
    },

    get aiDraftEdited() {
        const draft = this.state.aiDraft;
        return Boolean(draft && (this.state.composerText || "").trim() !== draft.text);
    },

    useAiDraft() {
        if (this.state.aiDraft) {
            this.state.composerText = this.state.aiDraft.text;
        }
    },

    async discardAiDraft() {
        const draft = this.state.aiDraft;
        if (!draft || !this.channelId) {
            return;
        }
        await this.orm.call("chatroom.channel", "action_ai_discard_draft", [this.channelId]);
        if ((this.state.composerText || "").trim() === draft.text) {
            this.state.composerText = "";
            this._storeDraft(this._composerChannelId, "");
        }
        this.state.aiDraft = false;
    },
});

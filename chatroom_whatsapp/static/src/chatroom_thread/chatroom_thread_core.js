/** @odoo-module **/

import { useService } from "@web/core/utils/hooks";
import { imageUrl } from "@web/core/utils/urls";
import { TagsList } from "@web/core/tags_list/tags_list";
import {
    Component,
    useState,
    useRef,
    onWillStart,
    onWillUpdateProps,
    onMounted,
    onPatched,
    onWillUnmount,
} from "@odoo/owl";

const MESSAGE_FIELDS = [
    "id",
    "direction",
    "message_type",
    "body",
    "state",
    "date",
    "attachment_ids",
    "reply_to_id",
    "sender_user_id",
    "sender_user_color",
    "retry_count",
    "wa_message_id",
    "own_reaction",
    "partner_reaction",
];

const REACTION_EMOJIS = ["👍", "❤️", "😂", "😮", "😢", "🙏"];

function odooDatetimeToDate(value) {
    if (!value) {
        return false;
    }
    return new Date(value.replace(" ", "T") + "Z");
}

/**
 * Hilo de conversación estilo WhatsApp (burbujas, adjuntos, notas de voz,
 * plantillas, botones rápidos, tiempo real). Recibe el id del canal por
 * prop en vez de depender de un registro de formulario, para poder
 * reutilizarse tanto en el campo `chatroom_thread` del formulario como en
 * la app de una sola pantalla (ver chatroom_app).
 */
export class ChatroomThreadCore extends Component {
    static template = "chatroom_whatsapp.ChatroomThreadCore";
    static components = { TagsList };
    static props = {
        channelId: { type: [Number, { value: false }], optional: true },
        emptyMessage: { type: String, optional: true },
        onOpenMobileSidebar: { type: Function, optional: true },
        onMessagesLoaded: { type: Function, optional: true },
        onChannelPriorityChanged: { type: Function, optional: true },
    };
    static defaultProps = {
        channelId: false,
        onChannelPriorityChanged: false,
        emptyMessage: "Seleccioná una conversación para empezar a chatear.",
    };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.busService = useService("bus_service");
        this.fileInput = useRef("fileInput");
        this.messagesRef = useRef("messages");
        this.REACTION_EMOJIS = REACTION_EMOJIS;

        this._busChannel = false;

        this.state = useState({
            loading: true,
            sending: false,
            dragOver: false,
            channelName: "",
            partnerId: false,
            partnerWriteDate: false,
            messages: [],
            composerText: "",
            pendingAttachments: [],
            recording: false,
            recordSeconds: 0,
            isSessionOpen: true,
            partnerOptedOut: false,
            quickButtonsOpen: false,
            quickButtons: ["", "", ""],
            cannedOpen: false,
            cannedResponses: [],
            lightboxUrl: false,
            noteMode: false,
            assignedUserId: false,
            assignedUserName: "",
            assignedUserInitials: "",
            assignedUserColor: "#94a3b8",
            reassignOpen: false,
            activity: false,
            calendarInstalled: false,
            activityMenuOpen: false,
            mentionOpen: false,
            mentionQuery: "",
            agents: [],
            replyingTo: false,
            reactingToId: false,
            numbers: [],
            whatsappNumberId: false,
            allTags: [],
            channelTagIds: [],
            tagPickerOpen: false,
            scheduledMessages: [],
            scheduleOpen: false,
            scheduleDate: "",
            aiPaused: false,
            manualUrgent: false,
            messageSearchOpen: false,
            messageSearch: "",
            newMessages: 0,
        });

        this._shouldScroll = true;
        this._onBusNotification = this._onBusNotification.bind(this);
        this._onAiUseResponse = this._onAiUseResponse.bind(this);
        // Se actualiza de forma síncrona (no esperando a que Owl confirme
        // los nuevos props) para saber qué canal ya se está cargando: el
        // propio _loadForCurrentRecord dispara onMessagesLoaded, que hace
        // que el padre (chatroom_app) vuelva a renderizar mientras este
        // onWillUpdateProps todavía está pendiente. Owl cancela ese fiber
        // y arranca uno nuevo antes de que this.props llegue a
        // actualizarse, así que comparar contra this.props.channelId deja
        // la comparación siempre en "distinto" y dispara la carga en
        // bucle infinito. Comparar contra este campo propio evita el bucle.
        this._loadedChannelId = false;

        onWillStart(() => {
            this._loadedChannelId = this.channelId;
            return this._loadForCurrentRecord();
        });

        onMounted(() => {
            this.busService.addEventListener("notification", this._onBusNotification);
            window.addEventListener("chatroom-ai-use-response", this._onAiUseResponse);
            this._scrollToBottom();
        });

        onPatched(() => {
            if (this._shouldScroll) {
                this._scrollToBottom();
                this._shouldScroll = false;
            }
        });

        onWillUpdateProps((nextProps) => {
            if (nextProps.channelId !== this._loadedChannelId) {
                this._loadedChannelId = nextProps.channelId;
                return this._loadForCurrentRecord(nextProps.channelId);
            }
        });

        onWillUnmount(() => {
            this.busService.removeEventListener("notification", this._onBusNotification);
            window.removeEventListener("chatroom-ai-use-response", this._onAiUseResponse);
            this._unsubscribeBus();
            this._stopMediaStream();
            clearInterval(this._recordingInterval);
        });
    }

    get channelId() {
        return this.props.channelId;
    }

    get visibleMessages() {
        const query = (this.state.messageSearch || "").trim().toLowerCase();
        if (!query) {
            return this.state.messages;
        }
        return this.state.messages.filter((message) =>
            (message.body || "").toLowerCase().includes(query)
            || (message.author_name || "").toLowerCase().includes(query)
        );
    }

    get messageSearchCount() {
        return this.state.messageSearch ? this.visibleMessages.length : 0;
    }

    toggleMessageSearch() {
        this.state.messageSearchOpen = !this.state.messageSearchOpen;
        if (!this.state.messageSearchOpen) {
            this.state.messageSearch = "";
        }
    }

    clearMessageSearch() {
        this.state.messageSearch = "";
    }

    onMessagesScroll() {
        if (this._isNearBottom()) {
            this.state.newMessages = 0;
        }
    }

    scrollToNewMessages() {
        this.state.newMessages = 0;
        this._shouldScroll = true;
        this._scrollToBottom();
    }

    _onAiUseResponse(ev) {
        const detail = ev.detail || {};
        if (detail.channelId !== this.channelId || !detail.text) {
            return;
        }
        this.state.noteMode = false;
        this.state.composerText = detail.text;
    }

    _subscribeBus(channelId) {
        if (channelId) {
            this._busChannel = `chatroom_channel_${channelId}`;
            this.busService.addChannel(this._busChannel);
        }
    }

    _unsubscribeBus() {
        if (this._busChannel) {
            this.busService.deleteChannel(this._busChannel);
            this._busChannel = false;
        }
    }

    async _loadForCurrentRecord(channelId = this.channelId) {
        this._unsubscribeBus();
        this.state.composerText = "";
        this.state.pendingAttachments = [];
        this.state.quickButtonsOpen = false;
        this.state.cannedOpen = false;
        this.state.noteMode = false;
        this.state.replyingTo = false;
        this.state.reactingToId = false;
        this.state.tagPickerOpen = false;
        this.state.scheduleOpen = false;
        this.state.scheduleDate = "";
        this.state.messageSearchOpen = false;
        this.state.messageSearch = "";
        this.state.newMessages = 0;
        this.state.messages = [];
        if (!channelId) {
            this.state.loading = false;
            this.state.messages = [];
            this.state.scheduledMessages = [];
            return;
        }
        this.state.loading = true;
        this._subscribeBus(channelId);
        await Promise.all([
            this._loadChannel(channelId),
            this._loadMessages(channelId),
            this._loadCannedResponses(),
            this._loadScheduledMessages(channelId),
        ]);
    }

    _onBusNotification({ detail: notifications }) {
        for (const { type, payload } of notifications) {
            if (type === "chatroom.message/new" && payload && payload.channel_id === this.channelId) {
                this._loadMessages();
                this._loadChannel();
            }
            if (type === "chatroom.message/waiting_response" && payload && payload.channel_id === this.channelId) {
                this.notification.add(
                    `${payload.partner_name || "El cliente"} está esperando respuesta en el chat.`,
                    { type: "warning", sticky: true }
                );
            }
        }
    }

    async _loadChannel(channelId = this.channelId) {
        if (!channelId) {
            return;
        }
        const [channel] = await this.orm.read(
            "chatroom.channel",
            [channelId],
            ["display_name", "partner_id", "channel_type", "is_session_open",
             "assigned_user_id", "assigned_user_initials", "assigned_user_color",
             "manual_urgent",
             "next_activity_id", "next_activity_summary", "next_activity_date_deadline",
             "next_activity_overdue", "next_activity_user_id", "calendar_installed",
             "whatsapp_number_id", "tag_ids", "ai_paused",
             "ai_sentiment", "ai_urgency"]
        );
        this.state.channelName = channel.display_name;
        this.state.partnerId = channel.partner_id ? channel.partner_id[0] : false;
        this.state.channelType = channel.channel_type;
        this.state.isSessionOpen = channel.is_session_open;
        this.state.assignedUserId = channel.assigned_user_id ? channel.assigned_user_id[0] : false;
        this.state.assignedUserName = channel.assigned_user_id ? channel.assigned_user_id[1] : "Sin asignar";
        this.state.assignedUserInitials = channel.assigned_user_initials || "";
        this.state.assignedUserColor = channel.assigned_user_color || "#94a3b8";
        this.state.manualUrgent = channel.manual_urgent;
        this.state.activity = channel.next_activity_id ? {
            id: channel.next_activity_id,
            summary: channel.next_activity_summary,
            date_deadline: channel.next_activity_date_deadline,
            overdue: channel.next_activity_overdue,
        } : false;
        this.state.calendarInstalled = channel.calendar_installed;
        this.state.activityMenuOpen = false;
        this.state.reassignOpen = false;
        this.state.whatsappNumberId = channel.whatsapp_number_id ? channel.whatsapp_number_id[0] : false;
        this.state.channelTagIds = channel.tag_ids || [];
        this.state.aiPaused = channel.ai_paused;
        this.state.aiSentiment = channel.ai_sentiment || false;
        this.state.aiUrgency = channel.ai_urgency || false;

        if (this.state.partnerId) {
            const [partner] = await this.orm.read(
                "res.partner", [this.state.partnerId], ["whatsapp_opt_out", "write_date"]);
            this.state.partnerOptedOut = partner.whatsapp_opt_out;
            this.state.partnerWriteDate = partner.write_date;
        } else {
            this.state.partnerOptedOut = false;
            this.state.partnerWriteDate = false;
        }
        if (!this.state.agents.length) {
            this.state.agents = await this.orm.call("chatroom.channel", "get_assignable_agents", []);
        }
        if (!this.state.numbers.length) {
            this.state.numbers = await this.orm.searchRead(
                "chatroom.whatsapp.number", [["active", "=", true]], ["name"], { order: "name" });
        }
        if (!this.state.allTags.length) {
            this.state.allTags = await this.orm.searchRead(
                "chatroom.tag", [], ["name", "color"], { order: "name" });
        }
    }

    async transferLine(ev) {
        if (!this.channelId) {
            return;
        }
        const newNumberId = parseInt(ev.target.value, 10) || false;
        await this.orm.write("chatroom.channel", [this.channelId], { whatsapp_number_id: newNumberId });
        this.state.whatsappNumberId = newNumberId;
        await Promise.all([this._loadChannel(), this._loadMessages()]);
    }

    async toggleManualUrgent() {
        if (!this.channelId) {
            return;
        }
        try {
            this.state.manualUrgent = await this.orm.call(
                "chatroom.channel", "action_toggle_manual_urgent", [this.channelId]);
            this.notification.add(
                this.state.manualUrgent ? "Conversación marcada como urgente."
                    : "Urgencia manual quitada.",
                { type: "success" }
            );
            if (this.props.onChannelPriorityChanged) {
                await this.props.onChannelPriorityChanged();
            }
        } catch (error) {
            this.notification.add(error.data ? error.data.message : error.message, {
                type: "danger",
            });
        }
    }

    async toggleAiPaused() {
        if (!this.channelId) {
            return;
        }
        const paused = await this.orm.call(
            "chatroom.channel", "action_toggle_ai_paused", [this.channelId]);
        this.state.aiPaused = paused;
        await this._loadMessages();
    }

    toggleTagPicker() {
        this.state.tagPickerOpen = !this.state.tagPickerOpen;
    }

    channelTagsForList() {
        return this.state.allTags
            .filter((tag) => this.state.channelTagIds.includes(tag.id))
            .map((tag) => ({
                id: tag.id,
                text: tag.name,
                colorIndex: tag.color,
                onDelete: () => this.removeTag(tag.id),
            }));
    }

    availableTags() {
        return this.state.allTags.filter((tag) => !this.state.channelTagIds.includes(tag.id));
    }

    async addTag(tagId) {
        if (!this.channelId) {
            return;
        }
        await this.orm.write("chatroom.channel", [this.channelId], { tag_ids: [[4, tagId]] });
        this.state.channelTagIds = [...this.state.channelTagIds, tagId];
        this.state.tagPickerOpen = false;
    }

    async removeTag(tagId) {
        if (!this.channelId) {
            return;
        }
        await this.orm.write("chatroom.channel", [this.channelId], { tag_ids: [[3, tagId]] });
        this.state.channelTagIds = this.state.channelTagIds.filter((id) => id !== tagId);
    }

    async reassign(ev) {
        const newUserId = parseInt(ev.target.value, 10);
        if (!newUserId || !this.channelId) {
            return;
        }
        await this.orm.write("chatroom.channel", [this.channelId], { assigned_user_id: newUserId });
        this.state.assignedUserId = newUserId;
    }

    toggleReassignMenu() {
        this.state.reassignOpen = !this.state.reassignOpen;
        this.state.activityMenuOpen = false;
    }

    async quickReassign(agent) {
        if (!this.channelId || !agent || agent.id === this.state.assignedUserId) {
            return;
        }
        try {
            const result = await this.orm.call(
                "chatroom.channel", "action_quick_reassign", [this.channelId], {
                    user_id: agent.id,
                });
            this.state.assignedUserId = result.assigned_user_id;
            this.state.assignedUserName = result.assigned_user_name;
            this.state.assignedUserInitials = result.assigned_user_initials;
            this.state.assignedUserColor = result.assigned_user_color;
            this.state.reassignOpen = false;
            this.notification.add(`Conversación asignada a ${result.assigned_user_name}.`, {
                type: "success",
            });
        } catch (error) {
            this.notification.add(error.data ? error.data.message : error.message, {
                type: "danger",
            });
        }
    }

    toggleActivityMenu() {
        this.state.activityMenuOpen = !this.state.activityMenuOpen;
        this.state.reassignOpen = false;
    }

    async _refreshActivity() {
        this.state.activity = await this.orm.call(
            "chatroom.channel", "get_next_activity_data", [this.channelId]);
        this.state.activityMenuOpen = false;
    }

    async markActivityDone() {
        if (!this.state.activity) {
            return;
        }
        try {
            await this.orm.call(
                "chatroom.channel", "action_mark_next_activity_done",
                [this.channelId, this.state.activity.id]);
            await this._refreshActivity();
        } catch (error) {
            this.notification.add(error.data ? error.data.message : error.message, {
                type: "danger",
            });
        }
    }

    async rescheduleActivityTomorrow() {
        if (!this.state.activity) {
            return;
        }
        try {
            await this.orm.call(
                "chatroom.channel", "action_reschedule_next_activity",
                [this.channelId, this.state.activity.id]);
            await this._refreshActivity();
        } catch (error) {
            this.notification.add(error.data ? error.data.message : error.message, {
                type: "danger",
            });
        }
    }

    async createFollowupActivity() {
        try {
            const action = await this.orm.call(
                "chatroom.channel", "action_open_activity_schedule", [this.channelId]);
            await this.action.doAction(action, {
                additionalContext: { dialog_size: "large" },
                onClose: () => this._refreshActivity(),
            });
        } catch (error) {
            this.notification.add(error.data ? error.data.message : error.message, {
                type: "danger",
            });
        }
    }

    async openCalendarMeeting() {
        try {
            const action = await this.orm.call(
                "chatroom.channel", "action_open_calendar_meeting", [this.channelId]);
            await this.action.doAction(action, {
                additionalContext: { dialog_size: "large" },
                onClose: () => this._refreshActivity(),
            });
        } catch (error) {
            this.notification.add(error.data ? error.data.message : error.message, {
                type: "danger",
            });
        }
    }

    activityLabel() {
        if (!this.state.activity) {
            return "Programar actividad";
        }
        if (this.state.activity.overdue) {
            const deadline = new Date(`${this.state.activity.date_deadline}T00:00:00`);
            const days = Math.max(1, Math.ceil((Date.now() - deadline.getTime()) / 86400000));
            return `¡URGENTE! ${this.state.activity.summary} vencido hace ${days} día${days === 1 ? '' : 's'}`;
        }
        const deadline = new Date(`${this.state.activity.date_deadline}T00:00:00`);
        return `Seguimiento: ${this.state.activity.summary} · ${deadline.toLocaleDateString()}`;
    }

    async _loadCannedResponses() {
        this.state.cannedResponses = await this.orm.searchRead(
            "chatroom.canned.response", [], ["name", "message"], { order: "name" });
    }

    toggleCannedResponses() {
        this.state.cannedOpen = !this.state.cannedOpen;
    }

    insertCannedResponse(message) {
        this.state.composerText = this.state.composerText
            ? `${this.state.composerText}\n${message}`
            : message;
        this.state.cannedOpen = false;
    }

    openSendTemplate() {
        if (!this.channelId) {
            return;
        }
        this.action.doAction("chatroom_whatsapp.action_chatroom_send_template_wizard", {
            additionalContext: { default_channel_id: this.channelId },
            onClose: () => this._loadMessages(),
        });
    }

    async _loadMessages(channelId = this.channelId) {
        if (!channelId) {
            this.state.loading = false;
            return;
        }
        const previousCount = this.state.messages.length;
        const wasNearBottom = this._isNearBottom() || !previousCount;
        const [messages, notes] = await Promise.all([
            this.orm.searchRead(
                "chatroom.message",
                [["channel_id", "=", channelId]],
                MESSAGE_FIELDS,
                { order: "date asc" }
            ),
            this.orm.call("chatroom.channel", "get_internal_notes", [channelId]),
        ]);
        const attachmentIds = [...new Set(messages.flatMap((m) => m.attachment_ids))];
        let attachmentsById = {};
        if (attachmentIds.length) {
            const attachments = await this.orm.read("ir.attachment", attachmentIds, [
                "name",
                "mimetype",
            ]);
            attachmentsById = Object.fromEntries(attachments.map((a) => [a.id, a]));
        }
        const messageItems = messages.map((m) => ({
            ...m,
            dateObj: odooDatetimeToDate(m.date),
            attachments: m.attachment_ids.map((id) => attachmentsById[id]).filter(Boolean),
        }));
        const noteItems = notes.map((n) => ({
            ...n,
            isNote: true,
            dateObj: odooDatetimeToDate(n.date),
            attachments: [],
        }));
        this.state.messages = [...messageItems, ...noteItems].sort(
            (a, b) => (a.dateObj || 0) - (b.dateObj || 0));
        this.state.loading = false;
        const addedMessages = Math.max(this.state.messages.length - previousCount, 0);
        this.state.newMessages = wasNearBottom ? 0 : this.state.newMessages + addedMessages;
        this._shouldScroll = wasNearBottom;

        const hasUnread = messages.some((m) => m.direction === "inbound" && m.state !== "read");
        if (hasUnread) {
            this.orm.call("chatroom.channel", "action_mark_read", [channelId]);
        }
        if (this.props.onMessagesLoaded) {
            this.props.onMessagesLoaded(channelId);
        }
    }

    isSameDay(a, b) {
        return Boolean(a) && Boolean(b)
            && a.getFullYear() === b.getFullYear()
            && a.getMonth() === b.getMonth()
            && a.getDate() === b.getDate();
    }

    isNewDay(index, messages = this.state.messages) {
        if (index === 0) {
            return true;
        }
        return !this.isSameDay(
            messages[index].dateObj,
            messages[index - 1].dateObj
        );
    }

    dateSeparatorLabel(dateObj) {
        if (!dateObj) {
            return "";
        }
        const now = new Date();
        const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        const day = new Date(dateObj.getFullYear(), dateObj.getMonth(), dateObj.getDate());
        const diffDays = Math.round((today - day) / 86400000);
        if (diffDays === 0) {
            return "Hoy";
        }
        if (diffDays === 1) {
            return "Ayer";
        }
        return dateObj.toLocaleDateString();
    }

    replyPreview(message) {
        if (!message.reply_to_id) {
            return false;
        }
        return this.state.messages.find((m) => m.id === message.reply_to_id[0]) || false;
    }

    canReply(message) {
        // Meta solo deja citar mensajes que ya tienen un wa_message_id
        // confirmado, y solo implementamos la cita del lado de WhatsApp
        // (Messenger/Instagram no están verificados con este flujo).
        return this.state.channelType === "whatsapp"
            && !message.isNote
            && Boolean(message.wa_message_id);
    }

    startReply(message) {
        this.state.replyingTo = message;
    }

    cancelReply() {
        this.state.replyingTo = false;
    }

    replyingToLabel() {
        const msg = this.state.replyingTo;
        if (!msg) {
            return "";
        }
        if (msg.direction === "inbound") {
            return this.state.channelName;
        }
        return this.senderName(msg) || "vos";
    }

    toggleReactionPicker(message) {
        this.state.reactingToId = this.state.reactingToId === message.id ? false : message.id;
    }

    async sendReaction(message, emoji) {
        this.state.reactingToId = false;
        const newEmoji = message.own_reaction === emoji ? "" : emoji;
        try {
            await this.orm.call(
                "chatroom.channel", "action_send_reaction",
                [this.channelId, message.id], { emoji: newEmoji });
            message.own_reaction = newEmoji || false;
        } catch (error) {
            this.notification.add(error.data ? error.data.message : error.message, {
                type: "danger",
            });
        }
    }

    toggleSchedule() {
        this.state.scheduleOpen = !this.state.scheduleOpen;
    }

    async sendLocation() {
        if (!this.channelId || this.state.sending) {
            return;
        }
        this.state.sending = true;
        try {
            await this.orm.call("chatroom.channel", "action_send_location", [this.channelId]);
            await this._loadMessages();
            await this._loadChannel();
        } catch (error) {
            this.notification.add(error.data ? error.data.message : error.message, {
                type: "danger",
            });
        } finally {
            this.state.sending = false;
        }
    }

    async exportPdf() {
        if (!this.channelId) {
            return;
        }
        try {
            const action = await this.orm.call(
                "chatroom.channel", "action_export_pdf", [this.channelId]);
            await this.action.doAction(action);
        } catch (error) {
            this.notification.add(error.data ? error.data.message : error.message, {
                type: "danger",
            });
        }
    }

    _localDatetimeToOdoo(localValue) {
        // El input datetime-local no trae zona horaria (se interpreta en
        // hora local del navegador); Date lo toma como tal, y toISOString
        // ya lo pasa a UTC, que es lo que espera el campo Datetime.
        const dt = new Date(localValue);
        return dt.toISOString().slice(0, 19).replace("T", " ");
    }

    async confirmSchedule() {
        const body = this.state.composerText.trim();
        if (!body) {
            this.notification.add("Escribe el mensaje que querés programar.", { type: "warning" });
            return;
        }
        if (!this.state.scheduleDate) {
            this.notification.add("Elegí fecha y hora para el envío.", { type: "warning" });
            return;
        }
        try {
            await this.orm.call(
                "chatroom.channel", "action_schedule_message", [this.channelId],
                { body, scheduled_date: this._localDatetimeToOdoo(this.state.scheduleDate) });
            this.state.composerText = "";
            this.state.scheduleOpen = false;
            this.state.scheduleDate = "";
            await this._loadScheduledMessages();
        } catch (error) {
            this.notification.add(error.data ? error.data.message : error.message, {
                type: "danger",
            });
        }
    }

    async _loadScheduledMessages(channelId = this.channelId) {
        if (!channelId) {
            this.state.scheduledMessages = [];
            return;
        }
        const items = await this.orm.call("chatroom.channel", "get_scheduled_messages", [channelId]);
        this.state.scheduledMessages = items.map((item) => ({
            ...item,
            dateObj: odooDatetimeToDate(item.scheduled_date),
        }));
    }

    async cancelScheduled(scheduledId) {
        if (!this.channelId) {
            return;
        }
        await this.orm.call(
            "chatroom.channel", "action_cancel_scheduled_message", [this.channelId, scheduledId]);
        await this._loadScheduledMessages();
    }

    formatScheduledDate(dateObj) {
        if (!dateObj) {
            return "";
        }
        return dateObj.toLocaleString(undefined, {
            day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
        });
    }

    async translateMessage(message) {
        if (message.translating) {
            return;
        }
        message.translating = true;
        try {
            message.translatedBody = await this.orm.call(
                "chatroom.message", "action_ai_translate", [message.id]);
        } catch (error) {
            this.notification.add(error.data ? error.data.message : error.message, {
                type: "danger",
            });
        } finally {
            message.translating = false;
        }
    }

    openLightbox(url) {
        this.state.lightboxUrl = url;
    }

    closeLightbox() {
        this.state.lightboxUrl = false;
    }

    _isNearBottom() {
        const el = this.messagesRef.el;
        if (!el) {
            return true;
        }
        return el.scrollHeight - el.scrollTop - el.clientHeight < 90;
    }

    _scrollToBottom() {
        const el = this.messagesRef.el;
        if (el) {
            el.scrollTop = el.scrollHeight;
        }
    }

    formatTime(dateObj) {
        if (!dateObj) {
            return "";
        }
        return dateObj.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
    }

    isImage(attachment) {
        return attachment && attachment.mimetype && attachment.mimetype.startsWith("image/");
    }

    isAudio(attachment) {
        return attachment && attachment.mimetype && attachment.mimetype.startsWith("audio/");
    }

    attachmentDownloadUrl(attachment) {
        return `/web/content/${attachment.id}?download=true`;
    }

    attachmentImageUrl(attachment) {
        return `/web/image/${attachment.id}`;
    }

    statusIcon(message) {
        if (message.direction !== "outbound") {
            return "";
        }
        return {
            sent: "fa-check",
            delivered: "fa-check-double text-muted",
            read: "fa-check-double text-primary",
            failed: "fa-exclamation-circle text-danger",
        }[message.state] || "fa-clock-o text-muted";
    }

    senderName(message) {
        return message.sender_user_id ? message.sender_user_id[1] : "";
    }

    senderInitials(message) {
        const name = this.senderName(message);
        return name ? name.split(/\s+/).slice(0, 2).map((part) => part[0]).join('').toUpperCase() : "";
    }

    senderColor(message) {
        if (message.sender_user_color) {
            return message.sender_user_color;
        }
        const palette = ["#3b82f6", "#16a34a", "#f59e0b", "#8b5cf6", "#ef4444", "#0891b2"];
        const id = message.sender_user_id ? message.sender_user_id[0] : 0;
        return palette[id % palette.length];
    }

    async retryMessage(message) {
        if (message.retrying || !this.channelId) {
            return;
        }
        message.retrying = true;
        try {
            await this.orm.call(
                "chatroom.channel", "action_retry_message", [this.channelId, message.id]);
            await this._loadMessages();
        } catch (error) {
            this.notification.add(error.data ? error.data.message : error.message, {
                type: "danger",
            });
        } finally {
            message.retrying = false;
        }
    }

    partnerAvatarUrl() {
        if (!this.state.partnerId) {
            return "";
        }
        // unique=write_date rompe el caché del navegador cuando se
        // sube una foto nueva -sin esto, el <img> seguía mostrando la
        // respuesta vieja cacheada aunque el campo ya hubiera cambiado.
        return imageUrl("res.partner", this.state.partnerId, "avatar_128", {
            unique: this.state.partnerWriteDate,
        });
    }

    openPartner() {
        if (!this.state.partnerId) {
            return;
        }
        // target "new" (diálogo encima) en vez de "current": abrir el
        // contacto no debe hacerte perder la conversación que tenías
        // abierta, ni en la app ni en el formulario clásico.
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "res.partner",
            res_id: this.state.partnerId,
            views: [[false, "form"]],
            target: "new",
        });
    }

    onComposerKeydown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.send();
        }
    }

    triggerFilePicker() {
        this.fileInput.el.click();
    }

    async onFileChange(ev) {
        await this._addFiles(ev.target.files);
        ev.target.value = "";
    }

    async onDrop(ev) {
        ev.preventDefault();
        this.state.dragOver = false;
        if (ev.dataTransfer && ev.dataTransfer.files.length) {
            await this._addFiles(ev.dataTransfer.files);
        }
    }

    onDragOver(ev) {
        ev.preventDefault();
        this.state.dragOver = true;
    }

    onDragLeave() {
        this.state.dragOver = false;
    }

    async _addFiles(fileList) {
        for (const file of fileList) {
            const data = await this._fileToBase64(file);
            this.state.pendingAttachments.push({
                name: file.name,
                mimetype: file.type,
                data,
                previewUrl: file.type.startsWith("image/") ? URL.createObjectURL(file) : false,
            });
        }
    }

    _fileToBase64(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result.split(",")[1]);
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
    }

    removePendingAttachment(index) {
        this.state.pendingAttachments.splice(index, 1);
    }

    // ------------------------------------------------------------------
    // Notas de voz (grabación con el micrófono del navegador)
    // ------------------------------------------------------------------
    async toggleRecording() {
        if (this.state.recording) {
            this._stopRecording(false);
        } else {
            await this._startRecording();
        }
    }

    cancelRecording() {
        this._stopRecording(true);
    }

    async _startRecording() {
        if (!navigator.mediaDevices || !window.MediaRecorder) {
            this.notification.add("Este navegador no soporta grabación de audio.", {
                type: "danger",
            });
            return;
        }
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            const supportedType = ["audio/ogg;codecs=opus", "audio/webm;codecs=opus", "audio/webm"]
                .find((type) => MediaRecorder.isTypeSupported(type));
            this._mediaStream = stream;
            this._recordedChunks = [];
            this._recordingCancelled = false;
            this.mediaRecorder = supportedType
                ? new MediaRecorder(stream, { mimeType: supportedType })
                : new MediaRecorder(stream);
            this.mediaRecorder.addEventListener("dataavailable", (ev) => {
                if (ev.data && ev.data.size) {
                    this._recordedChunks.push(ev.data);
                }
            });
            this.mediaRecorder.addEventListener("stop", () => this._onRecordingStop());
            this.mediaRecorder.start();
            this.state.recording = true;
            this.state.recordSeconds = 0;
            this._recordingInterval = setInterval(() => {
                this.state.recordSeconds++;
            }, 1000);
        } catch {
            this.notification.add(
                "No se pudo acceder al micrófono. Revisa los permisos del navegador.",
                { type: "danger" }
            );
        }
    }

    _stopRecording(cancelled) {
        this._recordingCancelled = cancelled;
        if (this.mediaRecorder && this.mediaRecorder.state !== "inactive") {
            this.mediaRecorder.stop();
        }
    }

    _stopMediaStream() {
        if (this._mediaStream) {
            this._mediaStream.getTracks().forEach((track) => track.stop());
            this._mediaStream = null;
        }
    }

    async _onRecordingStop() {
        clearInterval(this._recordingInterval);
        this.state.recording = false;
        this._stopMediaStream();

        if (this._recordingCancelled || !this._recordedChunks.length) {
            this._recordedChunks = [];
            return;
        }
        const mimetype = this.mediaRecorder.mimeType || "audio/webm";
        const blob = new Blob(this._recordedChunks, { type: mimetype });
        const extension = mimetype.includes("ogg") ? "ogg" : "webm";
        const data = await this._fileToBase64(blob);
        this.state.pendingAttachments.push({
            name: `nota_de_voz_${Date.now()}.${extension}`,
            mimetype,
            data,
            previewUrl: false,
            isVoiceNote: true,
        });
    }

    formatDuration(seconds) {
        const m = Math.floor(seconds / 60);
        const s = seconds % 60;
        return `${m}:${String(s).padStart(2, "0")}`;
    }

    // ------------------------------------------------------------------
    // Botones de respuesta rápida (WhatsApp Interactive Messages)
    // ------------------------------------------------------------------
    toggleQuickButtons() {
        this.state.quickButtonsOpen = !this.state.quickButtonsOpen;
        if (!this.state.quickButtonsOpen) {
            this.state.quickButtons = ["", "", ""];
        }
    }

    setQuickButton(index, value) {
        this.state.quickButtons[index] = value;
    }

    // ------------------------------------------------------------------
    // Notas internas (no se envían al cliente, quedan solo en Odoo)
    // ------------------------------------------------------------------
    toggleNoteMode() {
        this.state.noteMode = !this.state.noteMode;
        this.state.mentionOpen = false;
    }

    onComposerInput(ev) {
        this.state.composerText = ev.target.value;
        const match = this.state.composerText.match(/(?:^|\s)@([^\s@]*)$/);
        this.state.mentionQuery = match ? match[1].toLowerCase() : "";
        this.state.mentionOpen = Boolean(match && this.state.noteMode);
    }

    mentionAgents() {
        const query = this.state.mentionQuery;
        return this.state.agents.filter((agent) =>
            !query || agent.name.toLowerCase().includes(query)
            || agent.initials.toLowerCase().includes(query)
        );
    }

    insertMention(agent) {
        const name = (agent.name || '').replace(/\s+/g, '_');
        this.state.composerText = this.state.composerText.replace(
            /(?:^|\s)@[^\s@]*$/, (match) => `${match.startsWith(' ') ? ' ' : ''}@${name} `
        );
        this.state.mentionOpen = false;
        this.state.mentionQuery = "";
    }

    async send() {
        if (!this.channelId) {
            return;
        }
        const body = this.state.composerText.trim();
        if (this.state.noteMode) {
            if (!body) {
                return;
            }
            this.state.sending = true;
            try {
                await this.orm.call(
                    "chatroom.channel", "action_post_internal_note", [this.channelId], { body });
                this.state.composerText = "";
                this.state.noteMode = false;
                await this._loadMessages();
            } catch (error) {
                this.notification.add(error.data ? error.data.message : error.message, {
                    type: "danger",
                });
            } finally {
                this.state.sending = false;
            }
            return;
        }
        const attachments = this.state.pendingAttachments;
        const buttons = this.state.quickButtonsOpen
            ? this.state.quickButtons.filter((b) => b.trim())
            : [];
        if (!body && !attachments.length && !buttons.length) {
            return;
        }
        const replyToId = this.state.replyingTo ? this.state.replyingTo.id : false;
        this.state.sending = true;
        try {
            if (buttons.length) {
                await this.orm.call(
                    "chatroom.channel",
                    "action_send_interactive_buttons",
                    [this.channelId],
                    { body: body || false, buttons }
                );
                this.state.quickButtonsOpen = false;
                this.state.quickButtons = ["", "", ""];
            } else {
                await this.orm.call("chatroom.channel", "action_send_message", [this.channelId], {
                    body: body || false,
                    attachments: attachments.map(({ name, mimetype, data }) => ({
                        name,
                        mimetype,
                        data,
                    })),
                    reply_to_id: replyToId,
                });
            }
            this.state.composerText = "";
            this.state.pendingAttachments = [];
            this.state.replyingTo = false;
            await this._loadMessages();
            await this._loadChannel();
        } catch (error) {
            this.notification.add(error.data ? error.data.message : error.message, {
                type: "danger",
            });
        } finally {
            this.state.sending = false;
        }
    }
}

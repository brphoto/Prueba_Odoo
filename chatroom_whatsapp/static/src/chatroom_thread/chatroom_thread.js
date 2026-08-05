/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import {
    Component,
    useState,
    useRef,
    onWillStart,
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
];

function odooDatetimeToDate(value) {
    if (!value) {
        return false;
    }
    return new Date(value.replace(" ", "T") + "Z");
}

export class ChatroomThread extends Component {
    static template = "chatroom_whatsapp.ChatroomThread";
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.busService = useService("bus_service");
        this.fileInput = useRef("fileInput");
        this.messagesRef = useRef("messages");

        this.channelId = this.props.record.resId;
        this.busChannel = `chatroom_channel_${this.channelId}`;

        this.state = useState({
            loading: true,
            sending: false,
            dragOver: false,
            channelName: "",
            partnerId: false,
            messages: [],
            composerText: "",
            pendingAttachments: [],
        });

        this._shouldScroll = true;
        this._onBusNotification = this._onBusNotification.bind(this);

        onWillStart(async () => {
            await this._loadChannel();
            await this._loadMessages();
        });

        onMounted(() => {
            this.busService.addChannel(this.busChannel);
            this.busService.addEventListener("notification", this._onBusNotification);
            this._scrollToBottom();
        });

        onPatched(() => {
            if (this._shouldScroll) {
                this._scrollToBottom();
                this._shouldScroll = false;
            }
        });

        onWillUnmount(() => {
            this.busService.removeEventListener("notification", this._onBusNotification);
            this.busService.deleteChannel(this.busChannel);
        });
    }

    _onBusNotification({ detail: notifications }) {
        for (const { type, payload } of notifications) {
            if (type === "chatroom.message/new" && payload && payload.channel_id === this.channelId) {
                this._loadMessages();
            }
        }
    }

    async _loadChannel() {
        const [channel] = await this.orm.read(
            "chatroom.channel",
            [this.channelId],
            ["display_name", "partner_id", "channel_type"]
        );
        this.state.channelName = channel.display_name;
        this.state.partnerId = channel.partner_id ? channel.partner_id[0] : false;
        this.state.channelType = channel.channel_type;
    }

    async _loadMessages() {
        const messages = await this.orm.searchRead(
            "chatroom.message",
            [["channel_id", "=", this.channelId]],
            MESSAGE_FIELDS,
            { order: "date asc" }
        );
        const attachmentIds = [...new Set(messages.flatMap((m) => m.attachment_ids))];
        let attachmentsById = {};
        if (attachmentIds.length) {
            const attachments = await this.orm.read("ir.attachment", attachmentIds, [
                "name",
                "mimetype",
            ]);
            attachmentsById = Object.fromEntries(attachments.map((a) => [a.id, a]));
        }
        this.state.messages = messages.map((m) => ({
            ...m,
            dateObj: odooDatetimeToDate(m.date),
            attachments: m.attachment_ids.map((id) => attachmentsById[id]).filter(Boolean),
        }));
        this.state.loading = false;
        this._shouldScroll = true;
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

    openPartner() {
        if (!this.state.partnerId) {
            return;
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "res.partner",
            res_id: this.state.partnerId,
            views: [[false, "form"]],
            target: "current",
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

    async send() {
        const body = this.state.composerText.trim();
        const attachments = this.state.pendingAttachments;
        if (!body && !attachments.length) {
            return;
        }
        this.state.sending = true;
        try {
            await this.orm.call("chatroom.channel", "action_send_message", [this.channelId], {
                body: body || false,
                attachments: attachments.map(({ name, mimetype, data }) => ({
                    name,
                    mimetype,
                    data,
                })),
            });
            this.state.composerText = "";
            this.state.pendingAttachments = [];
            await this._loadMessages();
        } catch (error) {
            this.notification.add(error.data ? error.data.message : error.message, {
                type: "danger",
            });
        } finally {
            this.state.sending = false;
        }
    }
}

export const chatroomThreadField = {
    component: ChatroomThread,
    supportedTypes: ["one2many"],
};

registry.category("fields").add("chatroom_thread", chatroomThreadField);

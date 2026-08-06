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
            recording: false,
            recordSeconds: 0,
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
            this._stopMediaStream();
            clearInterval(this._recordingInterval);
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
        } catch (error) {
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

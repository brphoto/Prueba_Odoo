/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import { Component, useState, onWillStart, onMounted, onWillUnmount } from "@odoo/owl";
import { ChatroomThreadCore } from "../chatroom_thread/chatroom_thread_core";

const GLOBAL_BUS_CHANNEL = "chatroom_whatsapp_global";
const PINNED_NUMBER_STORAGE_KEY = "chatroom_whatsapp.pinned_number_id";

const CHANNEL_FIELDS = [
    "display_name",
    "channel_type",
    "last_message_preview",
    "last_message_date",
    "unread_count",
    "state",
    "partner_id",
    "assigned_user_id",
    "whatsapp_number_id",
];

const CHANNEL_ICONS = {
    whatsapp: "fa-whatsapp o_chatroom_channel_icon_whatsapp",
    messenger: "fa-facebook o_chatroom_channel_icon_messenger",
    instagram: "fa-instagram o_chatroom_channel_icon_instagram",
};

function odooDatetimeToDate(value) {
    if (!value) {
        return false;
    }
    return new Date(value.replace(" ", "T") + "Z");
}

function isSameDay(a, b) {
    return a.getFullYear() === b.getFullYear()
        && a.getMonth() === b.getMonth()
        && a.getDate() === b.getDate();
}

/**
 * App de una sola pantalla, estilo WhatsApp Web: lista de conversaciones a
 * la izquierda + hilo abierto a la derecha, sin navegar entre vistas.
 * Reutiliza ChatroomThreadCore (el mismo componente que usa el campo del
 * formulario clásico) para no duplicar la lógica de burbujas/adjuntos.
 */
export class ChatroomApp extends Component {
    static template = "chatroom_whatsapp.ChatroomApp";
    static components = { ChatroomThreadCore };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.busService = useService("bus_service");

        this.state = useState({
            loading: true,
            channels: [],
            numbers: [],
            selectedChannelId: false,
            searchText: "",
            filter: "all",
            numberFilter: this._getStoredNumberFilter(),
        });

        this._onBusNotification = this._onBusNotification.bind(this);

        onWillStart(async () => {
            await Promise.all([this._loadChannels(), this._loadNumbers()]);
        });

        onMounted(() => {
            this.busService.addChannel(GLOBAL_BUS_CHANNEL);
            this.busService.addEventListener("notification", this._onBusNotification);
        });

        onWillUnmount(() => {
            this.busService.removeEventListener("notification", this._onBusNotification);
        });
    }

    _getStoredNumberFilter() {
        try {
            return localStorage.getItem(PINNED_NUMBER_STORAGE_KEY) || "all";
        } catch {
            return "all";
        }
    }

    setNumberFilter(value) {
        this.state.numberFilter = value;
        try {
            localStorage.setItem(PINNED_NUMBER_STORAGE_KEY, value);
        } catch {
            // localStorage puede no estar disponible (modo privado, etc.):
            // el filtro sigue funcionando, solo no queda "pineado".
        }
        this._loadChannels();
    }

    setFilter(value) {
        this.state.filter = value;
        this._loadChannels();
    }

    onSearchInput(ev) {
        this.state.searchText = ev.target.value;
        this._debouncedReload();
    }

    _debouncedReload() {
        clearTimeout(this._searchTimeout);
        this._searchTimeout = setTimeout(() => this._loadChannels(), 300);
    }

    _onBusNotification({ detail: notifications }) {
        for (const { type } of notifications) {
            if (type === "chatroom.message/new") {
                this._loadChannels();
            }
        }
    }

    async _loadNumbers() {
        this.state.numbers = await this.orm.searchRead(
            "chatroom.whatsapp.number", [["active", "=", true]], ["name"], { order: "name" });
    }

    _buildDomain() {
        const domain = [];
        if (this.state.filter === "unread") {
            domain.push(["unread_count", ">", 0]);
        } else if (this.state.filter === "mine") {
            domain.push(["assigned_user_id", "=", user.userId]);
        }
        if (this.state.numberFilter === "mine") {
            domain.push(["whatsapp_number_id.member_ids", "in", [user.userId]]);
        } else if (this.state.numberFilter !== "all") {
            domain.push(["whatsapp_number_id", "=", parseInt(this.state.numberFilter, 10)]);
        }
        if (this.state.searchText.trim()) {
            const term = this.state.searchText.trim();
            domain.push("|", ["display_name", "ilike", term], ["partner_id", "ilike", term]);
        }
        return domain;
    }

    async _loadChannels() {
        this.state.loading = true;
        const channels = await this.orm.searchRead(
            "chatroom.channel", this._buildDomain(), CHANNEL_FIELDS,
            { order: "last_message_date desc", limit: 200 });
        this.state.channels = channels.map((c) => ({
            ...c,
            dateObj: odooDatetimeToDate(c.last_message_date),
        }));
        this.state.loading = false;
        if (this.state.selectedChannelId
                && !channels.some((c) => c.id === this.state.selectedChannelId)) {
            // La conversación abierta ya no entra en el filtro activo (p.ej.
            // se marcó como leída y el filtro es "No leídas"): no la cierro,
            // solo dejo de resaltarla en la lista.
        }
    }

    selectChannel(channelId) {
        this.state.selectedChannelId = channelId;
    }

    backToList() {
        this.state.selectedChannelId = false;
    }

    onThreadMessagesLoaded() {
        this._loadChannels();
    }

    channelIcon(channelType) {
        return CHANNEL_ICONS[channelType] || "fa-comment";
    }

    formatListTime(dateObj) {
        if (!dateObj) {
            return "";
        }
        const now = new Date();
        if (isSameDay(dateObj, now)) {
            return dateObj.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
        }
        return dateObj.toLocaleDateString(undefined, { day: "2-digit", month: "2-digit" });
    }
}

registry.category("actions").add("chatroom_whatsapp.chatroom_app", ChatroomApp);

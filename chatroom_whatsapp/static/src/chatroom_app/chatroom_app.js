/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import { Component, useState, onWillStart, onMounted, onWillUnmount } from "@odoo/owl";
import { ChatroomThreadCore } from "../chatroom_thread/chatroom_thread_core";
import { NewConversationDialog } from "./new_conversation_dialog";
import { ContactPanel } from "./contact_panel";

const CONTACT_PANEL_STORAGE_KEY = "chatroom_whatsapp.contact_panel_open";

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
    "assigned_user_initials",
    "assigned_user_color",
    "next_activity_id",
    "next_activity_summary",
    "next_activity_date_deadline",
    "next_activity_overdue",
    "first_response_sla_state",
    "pending_response_minutes",
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
    static components = { ChatroomThreadCore, ContactPanel };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.busService = useService("bus_service");
        this.dialogService = useService("dialog");
        this.action = useService("action");
        this.notification = useService("notification");

        this.state = useState({
            loading: true,
            channels: [],
            numbers: [],
            selectedChannelId: false,
            searchText: "",
            filter: "all",
            numberFilter: this._getStoredNumberFilter(),
            // En móvil el chat ocupa toda la pantalla y la ficha se abre
            // bajo demanda con el botón de contacto; en escritorio sí se
            // conserva la preferencia del usuario.
            contactPanelOpen: !this._isMobileViewport() && this._getStoredContactPanelOpen(),
            mobileSidebarOpen: false,
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
            // Busca por nombre del contacto/canal o por el contenido de
            // cualquier mensaje de la conversación (para encontrar "quién
            // preguntó por X" sin abrir chat por chat).
            domain.push(
                "|", "|",
                ["display_name", "ilike", term],
                ["partner_id", "ilike", term],
                ["message_ids.body", "ilike", term],
            );
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
        this.state.mobileSidebarOpen = false;
    }

    _getStoredContactPanelOpen() {
        try {
            return localStorage.getItem(CONTACT_PANEL_STORAGE_KEY) !== "0";
        } catch {
            return true;
        }
    }

    _isMobileViewport() {
        return Boolean(window.matchMedia && window.matchMedia("(max-width: 768px)").matches);
    }

    toggleContactPanel() {
        this.state.contactPanelOpen = !this.state.contactPanelOpen;
        if (this.state.contactPanelOpen) {
            this.state.mobileSidebarOpen = false;
        }
        try {
            localStorage.setItem(CONTACT_PANEL_STORAGE_KEY, this.state.contactPanelOpen ? "1" : "0");
        } catch {
            // Sin localStorage el toggle sigue funcionando, solo no se
            // recuerda entre sesiones.
        }
    }

    // ------------------------------------------------------------------
    // Herramientas del panel lateral
    // ------------------------------------------------------------------
    openNewConversation() {
        this.dialogService.add(NewConversationDialog, {
            onCreated: (channelId) => {
                this._loadChannels();
                this.selectChannel(channelId);
            },
        });
    }

    openTemplates() {
        this._openEmbeddedMenuAction("chatroom_whatsapp.action_chatroom_template");
    }

    openNumbers() {
        this._openEmbeddedMenuAction("chatroom_whatsapp.action_chatroom_whatsapp_number");
    }

    openCannedResponses() {
        this._openEmbeddedMenuAction("chatroom_whatsapp.action_chatroom_canned_response");
    }

    openDashboard() {
        this._openEmbeddedMenuAction("chatroom_whatsapp.action_chatroom_dashboard");
    }

    async _openEmbeddedMenuAction(xmlid) {
        try {
            const action = await this.orm.call(
                "chatroom.channel", "action_get_embedded_menu_action", [xmlid]);
            this.action.doAction(action, { onClose: () => this._loadChannels() });
        } catch (error) {
            this.notification.add(error.data ? error.data.message : error.message, {
                type: "danger",
            });
        }
    }

    async goToNextPending() {
        const domain = [["state", "=", "pending"]];
        if (this.state.selectedChannelId) {
            domain.push(["id", "!=", this.state.selectedChannelId]);
        }
        const [next] = await this.orm.searchRead(
            "chatroom.channel", domain, ["id"], { order: "last_message_date asc", limit: 1 });
        if (next) {
            this.selectChannel(next.id);
        } else {
            this.notification.add("No hay más conversaciones pendientes.", { type: "info" });
        }
    }

    backToList() {
        this.state.selectedChannelId = false;
        this.state.mobileSidebarOpen = false;
    }

    toggleMobileSidebar() {
        this.state.mobileSidebarOpen = !this.state.mobileSidebarOpen;
        if (this.state.mobileSidebarOpen) {
            this.state.contactPanelOpen = false;
        }
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

    activityLabel(channel) {
        if (!channel.next_activity_id) {
            return "";
        }
        const deadline = new Date(`${channel.next_activity_date_deadline}T00:00:00`);
        if (channel.next_activity_overdue) {
            const days = Math.max(1, Math.ceil((Date.now() - deadline.getTime()) / 86400000));
            return `Seguimiento vencido hace ${days} día${days === 1 ? '' : 's'}`;
        }
        const today = new Date();
        const tomorrow = new Date(today.getFullYear(), today.getMonth(), today.getDate() + 1);
        const label = deadline.toDateString() === tomorrow.toDateString()
            ? "Mañana" : deadline.toLocaleDateString(undefined, { day: "2-digit", month: "2-digit" });
        return `Siguiente actividad: ${label}`;
    }
}

registry.category("actions").add("chatroom_whatsapp.chatroom_app", ChatroomApp);

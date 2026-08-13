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
const SOUND_STORAGE_KEY = "chatroom_whatsapp.notification_sound";
const INBOX_FILTERS_STORAGE_KEY = "chatroom_whatsapp.inbox_filters";
const FILTERS_OPEN_STORAGE_KEY = "chatroom_whatsapp.filters_open";

const CHANNEL_FIELDS = [
    "display_name",
    "channel_type",
    "stage_id",
    "stage_name",
    "stage_color",
    "last_message_preview",
    "last_message_date",
    "manual_urgent",
    "is_pinned",
    "is_favorite",
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
            stageFilter: this._getStoredInboxFilter("stage", "all"),
            channelTypeFilter: this._getStoredInboxFilter("channel", "all"),
            stages: [],
            filtersOpen: this._getStoredFiltersOpen(),
            // En móvil el chat ocupa toda la pantalla y la ficha se abre
            // bajo demanda con el botón de contacto; en escritorio sí se
            // conserva la preferencia del usuario.
            contactPanelOpen: !this._isMobileViewport() && this._getStoredContactPanelOpen(),
            mobileSidebarOpen: false,
            soundEnabled: this._getStoredSoundEnabled(),
            desktopNotifications: this._getStoredDesktopNotifications(),
            companyLogoUrl: false,
            // El lanzador de Apps utiliza este mismo SVG; mantener una sola
            // fuente evita que el encabezado se vea distinto a Apps.
            appLogoUrl: "/chatroom_whatsapp/static/description/icon.svg",
            selectedChannelIds: [],
        });

        this._onBusNotification = this._onBusNotification.bind(this);
        this._onKeydown = this._onKeydown.bind(this);
        this._channelsLoadGeneration = 0;

        onWillStart(async () => {
            await Promise.all([this._loadChannels(), this._loadNumbers(), this._loadStages()]);
        });

        onMounted(() => {
            this.busService.addChannel(GLOBAL_BUS_CHANNEL);
            this.busService.addEventListener("notification", this._onBusNotification);
            window.addEventListener("keydown", this._onKeydown);
        });

        onWillUnmount(() => {
            this.busService.removeEventListener("notification", this._onBusNotification);
            window.removeEventListener("keydown", this._onKeydown);
            clearTimeout(this._searchTimeout);
            clearTimeout(this._busReloadTimeout);
        });
    }

    _getStoredNumberFilter() {
        try {
            return localStorage.getItem(PINNED_NUMBER_STORAGE_KEY) || "all";
        } catch {
            return "all";
        }
    }

    _getStoredSoundEnabled() {
        try {
            return localStorage.getItem(SOUND_STORAGE_KEY) === "1";
        } catch {
            return false;
        }
    }

    _getStoredDesktopNotifications() {
        try {
            return localStorage.getItem("chatroom_whatsapp.desktop_notifications") === "1";
        } catch {
            return false;
        }
    }

    _getStoredInboxFilter(name, fallback) {
        try {
            const filters = JSON.parse(localStorage.getItem(INBOX_FILTERS_STORAGE_KEY) || "{}");
            return filters[name] || fallback;
        } catch {
            return fallback;
        }
    }

    _storeInboxFilters() {
        try {
            localStorage.setItem(INBOX_FILTERS_STORAGE_KEY, JSON.stringify({
                stage: this.state.stageFilter,
                channel: this.state.channelTypeFilter,
            }));
        } catch {
            // El filtro sigue funcionando durante la sesión.
        }
    }

    _getStoredFiltersOpen() {
        try {
            return localStorage.getItem(FILTERS_OPEN_STORAGE_KEY) === "1";
        } catch {
            return false;
        }
    }

    toggleFilters() {
        this.state.filtersOpen = !this.state.filtersOpen;
        try {
            localStorage.setItem(
                FILTERS_OPEN_STORAGE_KEY,
                this.state.filtersOpen ? "1" : "0",
            );
        } catch {
            // El plegado sigue funcionando durante la sesión.
        }
    }

    async toggleDesktopNotifications() {
        if (!window.Notification) {
            this.notification.add("Este navegador no admite notificaciones de escritorio.", { type: "warning" });
            return;
        }
        if (Notification.permission !== "granted") {
            await Notification.requestPermission();
        }
        this.state.desktopNotifications = Notification.permission === "granted";
        try {
            localStorage.setItem(
                "chatroom_whatsapp.desktop_notifications",
                this.state.desktopNotifications ? "1" : "0");
        } catch {
            // Preferencia válida durante la sesión.
        }
    }

    toggleNotificationSound() {
        this.state.soundEnabled = !this.state.soundEnabled;
        try {
            localStorage.setItem(SOUND_STORAGE_KEY, this.state.soundEnabled ? "1" : "0");
        } catch {
            // El ajuste sigue funcionando durante la sesión.
        }
        if (this.state.soundEnabled) {
            this._playNotificationSound();
        }
    }

    _playNotificationSound() {
        if (!this.state.soundEnabled || !window.AudioContext && !window.webkitAudioContext) {
            return;
        }
        try {
            const AudioContextClass = window.AudioContext || window.webkitAudioContext;
            const context = new AudioContextClass();
            const oscillator = context.createOscillator();
            const gain = context.createGain();
            oscillator.frequency.value = 740;
            gain.gain.setValueAtTime(0.04, context.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.001, context.currentTime + 0.18);
            oscillator.connect(gain);
            gain.connect(context.destination);
            oscillator.start();
            oscillator.stop(context.currentTime + 0.18);
        } catch {
            // El navegador puede bloquear audio hasta que exista interacción.
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
        this.state.selectedChannelIds = [];
        this._loadChannels();
    }

    setStageFilter(value) {
        this.state.stageFilter = value;
        this._storeInboxFilters();
        this.state.selectedChannelIds = [];
        this._loadChannels();
    }

    setChannelTypeFilter(value) {
        this.state.channelTypeFilter = value;
        this._storeInboxFilters();
        this.state.selectedChannelIds = [];
        this._loadChannels();
    }

    clearInboxFilters() {
        this.state.filter = "all";
        this.state.numberFilter = "all";
        this.state.stageFilter = "all";
        this.state.channelTypeFilter = "all";
        this.state.searchText = "";
        this.state.selectedChannelIds = [];
        const searchInput = this.el?.querySelector(".o_chatroom_app_search input");
        if (searchInput) {
            searchInput.value = "";
        }
        this._storeInboxFilters();
        try {
            localStorage.removeItem(PINNED_NUMBER_STORAGE_KEY);
        } catch {
            // La limpieza sigue funcionando durante la sesión.
        }
        this._loadChannels();
    }

    hasActiveFilters() {
        return this.state.filter !== "all"
            || this.state.numberFilter !== "all"
            || this.state.stageFilter !== "all"
            || this.state.channelTypeFilter !== "all"
            || Boolean(this.state.searchText.trim());
    }

    activeFilterCount() {
        return [
            this.state.filter !== "all",
            this.state.numberFilter !== "all",
            this.state.stageFilter !== "all",
            this.state.channelTypeFilter !== "all",
            Boolean(this.state.searchText.trim()),
        ].filter(Boolean).length;
    }

    toggleChannelSelection(channelId) {
        const selected = new Set(this.state.selectedChannelIds);
        if (selected.has(channelId)) {
            selected.delete(channelId);
        } else {
            selected.add(channelId);
        }
        this.state.selectedChannelIds = [...selected];
    }

    allVisibleSelected() {
        return Boolean(this.state.channels.length)
            && this.state.channels.every((channel) =>
                this.state.selectedChannelIds.includes(channel.id));
    }

    toggleSelectAllVisible() {
        this.state.selectedChannelIds = this.allVisibleSelected()
            ? []
            : this.state.channels.map((channel) => channel.id);
    }

    async runBulkAction(methodName) {
        const ids = this.state.selectedChannelIds;
        if (!ids.length) {
            return;
        }
        try {
            await this.orm.call("chatroom.channel", methodName, [ids]);
            this.state.selectedChannelIds = [];
            await this._loadChannels();
            this.notification.add("Acción aplicada a las conversaciones seleccionadas.", {
                type: "success",
            });
        } catch (error) {
            this.notification.add(error.data ? error.data.message : error.message, {
                type: "danger",
            });
        }
    }

    async runBulkUrgency(urgent) {
        const ids = this.state.selectedChannelIds;
        if (!ids.length) {
            return;
        }
        try {
            await this.orm.call(
                "chatroom.channel", "action_bulk_set_manual_urgent", [ids, urgent]);
            this.state.selectedChannelIds = [];
            await this._loadChannels();
            this.notification.add(
                urgent ? "Conversaciones marcadas como urgentes." : "Urgencia retirada de las conversaciones.",
                { type: "success" },
            );
        } catch (error) {
            this.notification.add(error.data ? error.data.message : error.message, {
                type: "danger",
            });
        }
    }

    async runBulkStage(stageId) {
        const ids = this.state.selectedChannelIds;
        if (!ids.length || !stageId) {
            return;
        }
        try {
            await this.orm.call(
                "chatroom.channel", "action_bulk_set_stage", [ids, Number(stageId)]);
            this.state.selectedChannelIds = [];
            await this._loadChannels();
            this.notification.add("Etapa actualizada para las conversaciones seleccionadas.", {
                type: "success",
            });
        } catch (error) {
            this.notification.add(error.data ? error.data.message : error.message, {
                type: "danger",
            });
        }
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
        if (notifications.some(({ type }) => type === "chatroom.message/new")) {
            this._playNotificationSound();
            if (this.state.desktopNotifications && window.Notification
                    && Notification.permission === "granted") {
                new Notification("Nuevo mensaje en Chatroom", {
                    body: "Tienes una conversación pendiente de revisar.",
                    icon: "/chatroom_whatsapp/static/description/icon.svg",
                });
            }
            this._scheduleChannelsReload();
        }
    }

    _scheduleChannelsReload() {
        clearTimeout(this._busReloadTimeout);
        this._busReloadTimeout = setTimeout(() => this._loadChannels(), 250);
    }

    async _loadNumbers() {
        this.state.numbers = await this.orm.searchRead(
            "chatroom.whatsapp.number", [["active", "=", true]], ["name"], { order: "name" });
    }

    async _loadStages() {
        this.state.stages = await this.orm.searchRead(
            "chatroom.channel.stage", [["active", "=", true]], ["name", "sequence"],
            { order: "sequence, id" });
    }

    _buildDomain() {
        const domain = [];
        if (this.state.filter === "unread") {
            domain.push(["unread_count", ">", 0]);
        } else if (this.state.filter === "mine") {
            domain.push(["assigned_user_id", "=", user.userId]);
        } else if (this.state.filter === "pending") {
            domain.push(["state", "=", "pending"]);
        } else if (this.state.filter === "urgent") {
            // Estos dos indicadores dependen de la hora actual y no son
            // campos almacenados. No se pueden enviar como dominio SQL;
            // se filtran en _applyClientOnlyFilters después del searchRead.
        } else if (this.state.filter === "sla") {
            // El estado SLA se calcula en vivo y se filtra en el cliente.
        } else if (this.state.filter === "unassigned") {
            domain.push(["assigned_user_id", "=", false]);
        } else if (this.state.filter === "pinned") {
            domain.push(["is_pinned", "=", true]);
        } else if (this.state.filter === "favorites") {
            domain.push(["is_favorite", "=", true]);
        }
        if (this.state.stageFilter !== "all") {
            domain.push(["stage_id", "=", parseInt(this.state.stageFilter, 10)]);
        }
        if (this.state.channelTypeFilter !== "all") {
            domain.push(["channel_type", "=", this.state.channelTypeFilter]);
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

    _applyClientOnlyFilters(channels) {
        if (this.state.filter === "sla") {
            return channels.filter((channel) =>
                channel.first_response_sla_state === "yellow"
                || channel.first_response_sla_state === "red"
            );
        }
        if (this.state.filter !== "urgent") {
            return channels;
        }
        return channels.filter((channel) =>
            channel.manual_urgent
                || channel.next_activity_overdue
                || channel.first_response_sla_state === "red"
        );
    }

    async _loadChannelsLegacy() {
        this.state.loading = true;
        const channels = await this.orm.searchRead(
            "chatroom.channel", this._buildDomain(), CHANNEL_FIELDS,
            { order: "last_message_date desc", limit: 200 });
        this.state.channels = this._applyClientOnlyFilters(channels).map((c) => ({
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

    async _loadChannels() {
        const generation = ++this._channelsLoadGeneration;
        this.state.loading = true;
        try {
            const channels = await this.orm.searchRead(
                "chatroom.channel", this._buildDomain(), CHANNEL_FIELDS,
                { order: "last_message_date desc", limit: 200 });
            if (generation !== this._channelsLoadGeneration) {
                return;
            }
            this.state.channels = this._applyClientOnlyFilters(channels).map((c) => ({
                ...c,
                dateObj: odooDatetimeToDate(c.last_message_date),
            }));
        } catch (error) {
            if (generation === this._channelsLoadGeneration) {
                this.notification.add(error.data ? error.data.message : error.message, {
                    type: "danger",
                });
            }
        } finally {
            if (generation === this._channelsLoadGeneration) {
                this.state.loading = false;
            }
        }
    }

    selectChannel(channelId) {
        this.state.selectedChannelId = channelId;
        this.state.mobileSidebarOpen = false;
    }

    async toggleChannelFlag(channel, flag) {
        try {
            const value = await this.orm.call(
                "chatroom.channel", "action_toggle_flag", [channel.id, flag]);
            channel[flag] = value;
            this.state.channels = [...this.state.channels];
        } catch (error) {
            this.notification.add(error.data ? error.data.message : error.message, {
                type: "danger",
            });
        }
    }

    async toggleUrgent(channel) {
        try {
            const value = await this.orm.call(
                "chatroom.channel", "action_toggle_manual_urgent", [[channel.id]]);
            channel.manual_urgent = value;
            this.state.channels = [...this.state.channels];
        } catch (error) {
            this.notification.add(error.data ? error.data.message : error.message, {
                type: "danger",
            });
        }
    }

    _onKeydown(ev) {
        if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "k") {
            ev.preventDefault();
            this.el?.querySelector(".o_chatroom_app_search input")?.focus();
            return;
        }
        if (ev.key === "Escape" && this.state.contactPanelOpen) {
            this.toggleContactPanel();
        }
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

    async syncTemplates() {
        try {
            const result = await this.orm.call(
                "chatroom.template", "action_sync_templates", []);
            const params = result && result.params;
            this.notification.add(
                params ? `${params.title}: ${params.message}` : "Plantillas sincronizadas con Meta.",
                { type: params?.type || "success" }
            );
            this.openTemplates();
        } catch (error) {
            this.notification.add(error.data ? error.data.message : error.message, {
                type: "danger",
            });
        }
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

    stageColorClass(value) {
        const color = Math.max(0, Math.min(11, Number(value) || 0));
        return `o_chatroom_stage_color_${color}`;
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

/** @odoo-module **/

import { onMounted, onPatched, onWillStart, onWillUnmount } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";
import { ChatroomApp } from "@chatroom_whatsapp/chatroom_app/chatroom_app";

function hexToRgba(hex, alpha) {
    const match = /^#([0-9a-f]{6})$/i.exec(hex || "");
    if (!match) {
        return `rgba(0, 168, 132, ${alpha})`;
    }
    const value = parseInt(match[1], 16);
    return `rgba(${value >> 16}, ${(value >> 8) & 255}, ${value & 255}, ${alpha})`;
}

patch(ChatroomApp.prototype, {
    setup() {
        super.setup();
        this.chatroomUiSettings = false;
        this._chatroomUiRefresh = this._loadChatroomUiSettings.bind(this);
        onWillStart(async () => {
            await this._loadChatroomUiSettings();
        });
        onMounted(() => {
            this._applyChatroomUiSettings();
            window.addEventListener("chatroom_ui_settings_updated", this._chatroomUiRefresh);
            window.addEventListener("focus", this._chatroomUiRefresh);
        });
        // El contenido de la accion puede montar el nodo visual despues del
        // primer ciclo; reaplicar aqui evita que el tema quede solo guardado
        // en Ajustes sin reflejarse en la bandeja.
        onPatched(() => this._applyChatroomUiSettings());
        onWillUnmount(() => this._clearChatroomUiSettings());
    },

    async _loadChatroomUiSettings() {
        try {
            const settings = await this.orm.call(
                "chatroom.channel", "get_ui_settings", []);
            this.chatroomUiSettings = settings || {};
            if (this.state) {
                this.state.companyLogoUrl = this.chatroomUiSettings.logo_url || false;
            }
            this._applyChatroomUiSettings();
        } catch (error) {
            // The visual layer must never block the inbox if its optional
            // settings cannot be read.
            console.warn("Chatroom UI settings could not be loaded", error);
        }
    },

    _applyChatroomUiSettings() {
        const settings = this.chatroomUiSettings;
        if (!settings) {
            return;
        }
        const variables = {
            "--chatroom-ui-primary": settings.primary_color,
            "--chatroom-ui-primary-deep": settings.secondary_color,
            "--chatroom-ui-accent": settings.accent_color,
            "--chatroom-ui-outgoing-bubble": hexToRgba(settings.accent_color, 0.18),
            "--chatroom-ui-sidebar-width": `${settings.sidebar_width}px`,
            "--chatroom-ui-icon-scale": settings.icon_scale,
            "--chatroom-ui-font-scale": settings.font_scale,
            "--chatroom-ui-shadow": settings.shadow_level === "high"
                ? "0 18px 42px rgba(15, 23, 42, 0.18)"
                : settings.shadow_level === "low"
                    ? "0 4px 12px rgba(15, 23, 42, 0.06)"
                    : "0 12px 34px rgba(15, 23, 42, 0.10)",
            "--chatroom-ui-bubble-radius": `${settings.bubble_radius}px`,
            "--chatroom-ui-message-gap": settings.message_gap,
            "--chatroom-ui-bubble-padding": settings.bubble_padding,
        };
        const roots = [...document.querySelectorAll(".o_chatroom_app")];
        if (this.el?.classList.contains("o_chatroom_app") && !roots.includes(this.el)) {
            roots.push(this.el);
        }
        const targets = [...roots, document.documentElement].filter(Boolean);
        targets.forEach((target) => Object.entries(variables).forEach(([name, value]) => {
            if (value !== undefined && value !== null && value !== "") {
                target.style.setProperty(name, value);
            }
        }));
        if (settings.background_image) {
            targets.forEach((target) => {
                target.style.setProperty(
                    "--chatroom-ui-chat-background",
                    `url("${settings.background_image}")`
                );
                target.style.setProperty("--chatroom-ui-chat-background-size", "cover");
                target.style.setProperty("--chatroom-ui-chat-background-repeat", "no-repeat");
            });
        } else {
            targets.forEach((target) => {
                target.style.removeProperty("--chatroom-ui-chat-background");
                target.style.removeProperty("--chatroom-ui-chat-background-size");
                target.style.removeProperty("--chatroom-ui-chat-background-repeat");
            });
        }
    },

    _clearChatroomUiSettings() {
        const root = this.el?.classList.contains("o_chatroom_app")
            ? this.el
            : this.el?.querySelector(".o_chatroom_app");
        const targets = [root, document.documentElement].filter(Boolean);
        const names = [
            "--chatroom-ui-primary",
            "--chatroom-ui-primary-deep",
            "--chatroom-ui-accent",
            "--chatroom-ui-outgoing-bubble",
            "--chatroom-ui-sidebar-width",
            "--chatroom-ui-icon-scale",
            "--chatroom-ui-font-scale",
            "--chatroom-ui-shadow",
            "--chatroom-ui-bubble-radius",
            "--chatroom-ui-message-gap",
            "--chatroom-ui-bubble-padding",
            "--chatroom-ui-chat-background",
            "--chatroom-ui-chat-background-size",
            "--chatroom-ui-chat-background-repeat",
        ];
        targets.forEach((target) => names.forEach((name) => target.style.removeProperty(name)));
        window.removeEventListener("chatroom_ui_settings_updated", this._chatroomUiRefresh);
        window.removeEventListener("focus", this._chatroomUiRefresh);
    },
});

// If the administrator changes the theme while Chatroom is still mounted,
// notify it immediately. When the app is opened later, its onWillStart call
// still reads the persisted company values, so this is only an acceleration
// of the normal flow and never the source of truth.
patch(FormController.prototype, {
    async onRecordSaved(record, changes) {
        await super.onRecordSaved(record, changes);
        if (record.resModel === "res.config.settings") {
            window.dispatchEvent(new Event("chatroom_ui_settings_updated"));
        }
    },
});

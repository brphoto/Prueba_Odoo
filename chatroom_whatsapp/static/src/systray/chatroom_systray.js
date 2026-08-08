/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import { Component, useState, onWillStart, onMounted, onWillUnmount } from "@odoo/owl";

const GLOBAL_BUS_CHANNEL = "chatroom_whatsapp_global";

/** Un "ding" corto generado con Web Audio, sin depender de ningún
 * archivo de sonido (evita problemas de tamaño/licencia de un asset). */
function playNotificationSound() {
    try {
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        const ctx = new AudioContextClass();
        const oscillator = ctx.createOscillator();
        const gain = ctx.createGain();
        oscillator.connect(gain);
        gain.connect(ctx.destination);
        oscillator.type = "sine";
        oscillator.frequency.setValueAtTime(880, ctx.currentTime);
        gain.gain.setValueAtTime(0.15, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.35);
        oscillator.start();
        oscillator.stop(ctx.currentTime + 0.35);
    } catch {
        // Autoplay bloqueado (sin interacción previa del usuario) u otro
        // problema de audio: no es crítico, se sigue sin sonido.
    }
}

export class ChatroomSystrayIcon extends Component {
    static template = "chatroom_whatsapp.SystrayIcon";
    static props = [];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.busService = useService("bus_service");

        this.state = useState({ visible: false, count: 0, urgent: 0, crmRed: 0 });
        this._onBusNotification = this._onBusNotification.bind(this);

        onWillStart(async () => {
            this.state.visible = await user.hasGroup("chatroom_whatsapp.group_chatroom_user");
            if (this.state.visible) {
                await this._loadCount();
            }
        });

        onMounted(() => {
            if (this.state.visible) {
                this.busService.addChannel(GLOBAL_BUS_CHANNEL);
                this.busService.addEventListener("notification", this._onBusNotification);
                if (window.Notification && Notification.permission === "default") {
                    Notification.requestPermission();
                }
            }
        });

        onWillUnmount(() => {
            this.busService.removeEventListener("notification", this._onBusNotification);
        });
    }

    _onBusNotification({ detail: notifications }) {
        for (const { type, payload } of notifications) {
            if (type === "chatroom.message/new") {
                this._loadCount();
            } else if (type === "chatroom.message/inbound") {
                this._onNewInboundMessage(payload);
            }
        }
    }

    _onNewInboundMessage(payload) {
        if (!payload) {
            return;
        }
        // Avisar solo si es mío o todavía no tiene agente asignado: no
        // hace falta que suene/aparezca para las conversaciones de todo
        // el resto del equipo.
        if (payload.assigned_user_id && payload.assigned_user_id !== user.userId) {
            return;
        }
        playNotificationSound();
        if (window.Notification && Notification.permission === "granted") {
            const notification = new Notification(`WhatsApp: ${payload.partner_name}`, {
                body: payload.preview || "Nuevo mensaje",
                icon: "/chatroom_whatsapp/static/description/icon.png",
                tag: `chatroom-${payload.channel_id}`,
            });
            notification.onclick = () => {
                window.focus();
                this.openChatroom();
                notification.close();
            };
        }
    }

    async _loadCount() {
        const values = await Promise.all([
            this.orm.searchCount("chatroom.channel", [["state", "=", "pending"]]),
            this.orm.searchCount("chatroom.channel", [["manual_urgent", "=", true]]),
        ]);
        this.state.count = values[0];
        this.state.urgent = values[1];
        try {
            const alerts = await this.orm.call("crm.lead", "get_management_alert_counts", []);
            this.state.crmRed = alerts.red || 0;
        } catch {
            this.state.crmRed = 0;
        }
    }

    openChatroom() {
        this.action.doAction("chatroom_whatsapp.action_chatroom_app");
    }
}

registry
    .category("systray")
    .add("chatroom_whatsapp.systray", { Component: ChatroomSystrayIcon }, { sequence: 21 });

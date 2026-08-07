/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ChatroomApp } from "@chatroom_whatsapp/chatroom_app/chatroom_app";

/**
 * Agrega la categoría RFM y la alerta de seguimiento a la lista de
 * conversaciones de la app de una sola pantalla. Se hace con una segunda
 * lectura liviana después de la carga normal, en vez de tocar el domain
 * o los campos de _loadChannels en chatroom_whatsapp, para no acoplarse
 * a los detalles internos de ese método.
 */
patch(ChatroomApp.prototype, {
    async _loadChannels() {
        await super._loadChannels();
        const ids = this.state.channels.map((c) => c.id);
        if (!ids.length) {
            return;
        }
        const extra = await this.orm.read(
            "chatroom.channel", ids, ["rfm_category", "management_alert_state"]);
        const byId = Object.fromEntries(extra.map((e) => [e.id, e]));
        this.state.channels = this.state.channels.map((c) => ({
            ...c,
            rfm_category: byId[c.id] ? byId[c.id].rfm_category : false,
            management_alert_state: byId[c.id] ? byId[c.id].management_alert_state : "green",
        }));
    },
});

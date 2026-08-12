/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ContactPanel } from "@chatroom_whatsapp/chatroom_app/contact_panel";

/**
 * Agrega el acceso a Calendario (agendar/ver reuniones) al panel de
 * contacto del chatroom, sin tocar chatroom_whatsapp: mismo criterio de
 * extensión por patch() que ya usa chatroom_sales_intelligence.
 */
patch(ContactPanel.prototype, {
    async scheduleMeeting() {
        try {
            const result = await this.orm.call(
                "chatroom.channel", "action_schedule_meeting", [this.props.channelId]);
            this._openDialog(result);
        } catch (error) {
            this.notification.add(error.data ? error.data.message : error.message, {
                type: "danger",
            });
        }
    },

    async viewMeetings() {
        try {
            const result = await this.orm.call(
                "chatroom.channel", "action_view_meetings", [this.props.channelId]);
            // _openDialog fuerza target: "new" igual para cualquier acción
            // (ver su definición en contact_panel.js): no hace falta -ni
            // existe en esta clase- un "_openInNewTab" aparte para el caso
            // de varias reuniones, es el mismo patrón que usan todos los
            // demás botones de este panel (openLeads, openProductCatalog, etc).
            this._openDialog(result);
        } catch (error) {
            this.notification.add(error.data ? error.data.message : error.message, {
                type: "danger",
            });
        }
    },
});

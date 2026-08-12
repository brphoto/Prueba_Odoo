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
            if (result.target === "new") {
                this._openDialog(result);
            } else {
                this._openInNewTab(result);
            }
        } catch (error) {
            this.notification.add(error.data ? error.data.message : error.message, {
                type: "danger",
            });
        }
    },
});

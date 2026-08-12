/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ChatroomSystrayIcon } from "@chatroom_whatsapp/systray/chatroom_systray";

/**
 * Agrega el contador de oportunidades en rojo (crm.lead) al systray del
 * chatroom, sin tocar chatroom_whatsapp: ese módulo no depende de
 * crm_customer_intelligence ni sabe que "get_management_alert_counts"
 * existe. Este módulo sí depende de los dos, así que es el lugar
 * correcto para unir ambas cosas (mismo criterio que el resto de los
 * patches de este módulo).
 */
patch(ChatroomSystrayIcon.prototype, {
    async _loadCount() {
        await super._loadCount();
        try {
            const alerts = await this.orm.call("crm.lead", "get_management_alert_counts", []);
            this.state.crmRed = alerts.red || 0;
        } catch {
            this.state.crmRed = 0;
        }
    },
});

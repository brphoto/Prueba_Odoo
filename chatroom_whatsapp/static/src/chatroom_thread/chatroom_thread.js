/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component } from "@odoo/owl";
import { ChatroomThreadCore } from "./chatroom_thread_core";

/**
 * Widget de campo one2many (message_ids) para el formulario de
 * chatroom.channel: delega todo el trabajo en ChatroomThreadCore, que
 * también se reutiliza en la app de una sola pantalla (chatroom_app).
 * La única responsabilidad propia de este wrapper es resolver el id del
 * registro y mostrar un aviso mientras el registro es nuevo (sin guardar).
 */
export class ChatroomThread extends Component {
    static template = "chatroom_whatsapp.ChatroomThread";
    static components = { ChatroomThreadCore };
    static props = { ...standardFieldProps };

    get channelId() {
        return this.props.record.resId || false;
    }
}

export const chatroomThreadField = {
    component: ChatroomThread,
    supportedTypes: ["one2many"],
};

registry.category("fields").add("chatroom_thread", chatroomThreadField);

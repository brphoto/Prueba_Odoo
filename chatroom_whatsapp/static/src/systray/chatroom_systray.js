/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import { Component, useState, onWillStart, onMounted, onWillUnmount } from "@odoo/owl";

const GLOBAL_BUS_CHANNEL = "chatroom_whatsapp_global";

export class ChatroomSystrayIcon extends Component {
    static template = "chatroom_whatsapp.SystrayIcon";
    static props = [];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.busService = useService("bus_service");

        this.state = useState({ visible: false, count: 0 });
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
            }
        });

        onWillUnmount(() => {
            this.busService.removeEventListener("notification", this._onBusNotification);
        });
    }

    _onBusNotification({ detail: notifications }) {
        for (const { type } of notifications) {
            if (type === "chatroom.message/new") {
                this._loadCount();
            }
        }
    }

    async _loadCount() {
        this.state.count = await this.orm.searchCount("chatroom.channel", [["state", "=", "pending"]]);
    }

    openChatroom() {
        this.action.doAction("chatroom_whatsapp.action_chatroom_app");
    }
}

registry
    .category("systray")
    .add("chatroom_whatsapp.systray", { Component: ChatroomSystrayIcon }, { sequence: 21 });

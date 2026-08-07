/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";

/**
 * Diálogo para iniciar una conversación de WhatsApp por nosotros (no
 * esperar a que el cliente escriba primero): elegir un contacto existente
 * o crear uno nuevo al vuelo, con su número, y abrir/crear el canal.
 * Útil para seguimiento, encuestas, avisos, etc. — como la conversación
 * es nueva, va a estar fuera de la ventana de 24h casi siempre, así que
 * el chat va a pedir una plantilla para el primer mensaje.
 */
export class NewConversationDialog extends Component {
    static template = "chatroom_whatsapp.NewConversationDialog";
    static components = { Dialog };
    static props = {
        close: Function,
        onCreated: Function,
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");

        this.state = useState({
            searchText: "",
            searchResults: [],
            selectedPartner: false,
            creatingNew: false,
            newName: "",
            newPhone: "",
            phone: "",
            numbers: [],
            whatsappNumberId: false,
            saving: false,
        });

        onWillStart(async () => {
            this.state.numbers = await this.orm.searchRead(
                "chatroom.whatsapp.number", [["active", "=", true]], ["name"], { order: "name" });
        });
    }

    onSearchInput(ev) {
        this.state.searchText = ev.target.value;
        this.state.selectedPartner = false;
        clearTimeout(this._searchTimeout);
        if (this.state.searchText.trim().length < 2) {
            this.state.searchResults = [];
            return;
        }
        this._searchTimeout = setTimeout(() => this._search(), 300);
    }

    async _search() {
        this.state.searchResults = await this.orm.searchRead(
            "res.partner",
            [["name", "ilike", this.state.searchText.trim()]],
            ["name", "phone"],
            { limit: 8 }
        );
    }

    selectPartner(partner) {
        this.state.selectedPartner = partner;
        this.state.phone = partner.phone || "";
        this.state.searchText = partner.name;
        this.state.searchResults = [];
        this.state.creatingNew = false;
    }

    clearSelection() {
        this.state.selectedPartner = false;
        this.state.searchText = "";
        this.state.phone = "";
    }

    toggleCreateNew() {
        this.state.creatingNew = !this.state.creatingNew;
        this.state.selectedPartner = false;
        this.state.searchText = "";
        this.state.searchResults = [];
    }

    async confirm() {
        if (this.state.saving) {
            return;
        }
        let partnerId = this.state.selectedPartner ? this.state.selectedPartner.id : false;
        let phone = this.state.phone.trim();

        if (this.state.creatingNew) {
            if (!this.state.newName.trim() || !this.state.newPhone.trim()) {
                this.notification.add("Escribí el nombre y el número del contacto nuevo.", {
                    type: "warning",
                });
                return;
            }
            phone = this.state.newPhone.trim();
        } else if (!partnerId) {
            this.notification.add("Elegí un contacto o creá uno nuevo.", { type: "warning" });
            return;
        }
        if (!phone) {
            this.notification.add("Falta el número de WhatsApp.", { type: "warning" });
            return;
        }

        this.state.saving = true;
        try {
            if (this.state.creatingNew) {
                partnerId = await this.orm.create("res.partner", [{
                    name: this.state.newName.trim(),
                    phone,
                }]);
                partnerId = partnerId[0];
            }
            const channelId = await this.orm.call(
                "chatroom.channel", "action_start_conversation", [],
                {
                    partner_id: partnerId,
                    phone,
                    whatsapp_number_id: this.state.whatsappNumberId
                        ? parseInt(this.state.whatsappNumberId, 10) : false,
                }
            );
            this.props.onCreated(channelId);
            this.props.close();
        } catch (error) {
            this.notification.add(error.data ? error.data.message : error.message, {
                type: "danger",
            });
        } finally {
            this.state.saving = false;
        }
    }
}

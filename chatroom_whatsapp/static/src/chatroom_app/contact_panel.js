/** @odoo-module **/

import { useService } from "@web/core/utils/hooks";
import { Component, useState, onWillStart, onWillUpdateProps } from "@odoo/owl";

/**
 * Panel lateral de la app con los datos del contacto y accesos rápidos a
 * CRM/Ventas/Compras/Facturas/Tareas — para no tener que salir del chat
 * a buscar esa info cuando se está vendiendo por WhatsApp. También deja
 * mandar el PDF de un presupuesto o factura ya existente directo por la
 * conversación (adjunto, como cualquier otro archivo).
 */
export class ContactPanel extends Component {
    static template = "chatroom_whatsapp.ContactPanel";
    static props = {
        channelId: { type: [Number, { value: false }], optional: true },
    };
    static defaultProps = {
        channelId: false,
    };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        this.state = useState({
            loading: true,
            data: false,
            sendingDocKey: false,
            productQuery: "",
            productResults: [],
            sendingProductId: false,
        });

        onWillStart(() => this._load(this.props.channelId));
        onWillUpdateProps((nextProps) => {
            if (nextProps.channelId !== this.props.channelId) {
                return this._load(nextProps.channelId);
            }
        });
    }

    async _load(channelId) {
        this.state.productQuery = "";
        this.state.productResults = [];
        if (!channelId) {
            this.state.data = false;
            this.state.loading = false;
            return;
        }
        this.state.loading = true;
        this.state.data = await this.orm.call(
            "chatroom.channel", "get_contact_panel_data", [channelId]);
        this.state.loading = false;
        if (this.state.data.product_installed) {
            this._searchProducts();
        }
    }

    async _reload() {
        await this._load(this.props.channelId);
    }

    formatMoney(amount, symbol) {
        const value = (amount || 0).toLocaleString(undefined, {
            minimumFractionDigits: 2, maximumFractionDigits: 2,
        });
        return symbol ? `${value} ${symbol}` : value;
    }

    openPartner() {
        if (!this.state.data || !this.state.data.partner_id) {
            return;
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "res.partner",
            res_id: this.state.data.partner_id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    async _openChannelAction(methodName) {
        const result = await this.orm.call(
            "chatroom.channel", methodName, [this.props.channelId]);
        this.action.doAction(result);
    }

    openLeads() {
        this._openChannelAction("action_view_leads");
    }

    openSaleOrders() {
        this._openChannelAction("action_view_sale_orders");
    }

    openPurchases() {
        this._openChannelAction("action_view_purchases");
    }

    openInvoices() {
        this._openChannelAction("action_view_invoices");
    }

    openTasks() {
        this._openChannelAction("action_view_tasks");
    }

    async createLead() {
        await this._openChannelAction("action_create_lead");
        await this._reload();
    }

    async createQuotation() {
        await this._openChannelAction("action_create_quotation");
        await this._reload();
    }

    async createTask() {
        await this._openChannelAction("action_create_task");
        await this._reload();
    }

    async sendOrderPdf(order) {
        await this._sendDocPdf(`order-${order.id}`, "action_send_sale_order_pdf", order.id);
    }

    async sendInvoicePdf(invoice) {
        await this._sendDocPdf(`invoice-${invoice.id}`, "action_send_invoice_pdf", invoice.id);
    }

    async _sendDocPdf(key, methodName, resId) {
        if (this.state.sendingDocKey) {
            return;
        }
        this.state.sendingDocKey = key;
        try {
            await this.orm.call("chatroom.channel", methodName, [this.props.channelId, resId]);
            this.notification.add("Documento enviado por WhatsApp.", { type: "success" });
        } catch (error) {
            this.notification.add(error.data ? error.data.message : error.message, {
                type: "danger",
            });
        } finally {
            this.state.sendingDocKey = false;
        }
    }

    // ------------------------------------------------------------------
    // Catálogo de productos
    // ------------------------------------------------------------------
    onProductSearchInput(ev) {
        this.state.productQuery = ev.target.value;
        clearTimeout(this._productSearchTimeout);
        this._productSearchTimeout = setTimeout(() => this._searchProducts(), 300);
    }

    async _searchProducts() {
        this.state.productResults = await this.orm.call(
            "chatroom.channel", "search_products", [this.state.productQuery]);
    }

    productImageUrl(product) {
        return `/web/image/product.product/${product.id}/image_128`;
    }

    openProductCatalog() {
        this.orm.call("chatroom.channel", "action_view_products", []).then(
            (result) => this.action.doAction(result));
    }

    async sendProduct(product) {
        if (this.state.sendingProductId) {
            return;
        }
        this.state.sendingProductId = product.id;
        try {
            await this.orm.call(
                "chatroom.channel", "action_send_product", [this.props.channelId, product.id]);
            this.notification.add("Producto enviado por WhatsApp.", { type: "success" });
        } catch (error) {
            this.notification.add(error.data ? error.data.message : error.message, {
                type: "danger",
            });
        } finally {
            this.state.sendingProductId = false;
        }
    }
}

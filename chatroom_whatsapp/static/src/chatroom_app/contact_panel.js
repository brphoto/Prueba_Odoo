/** @odoo-module **/

import { useService } from "@web/core/utils/hooks";
import { imageUrl } from "@web/core/utils/urls";
import { Component, useState, onWillStart, onWillUpdateProps, onMounted, onWillUnmount } from "@odoo/owl";

const COLLAPSED_SECTIONS_STORAGE_KEY = "chatroom_whatsapp.contact_panel_collapsed_sections";

/**
 * Panel lateral de la app con los datos del contacto y accesos rápidos a
 * CRM/Ventas/Compras/Facturas/Tareas — para no tener que salir del chat
 * a buscar esa info cuando se está vendiendo por WhatsApp. También deja
 * mandar el PDF de un presupuesto o factura ya existente directo por la
 * conversación (adjunto, como cualquier otro archivo).
 */
export class ContactPanel extends Component {
    static template = "chatroom_whatsapp.ContactPanel";
    static components = {};
    static props = {
        channelId: { type: [Number, { value: false }], optional: true },
        onClose: { type: Function, optional: true },
    };
    static defaultProps = {
        channelId: false,
        onClose: false,
    };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        this.state = useState({
            loading: true,
            data: false,
            sendingDocKey: false,
            completingActivityId: false,
            productQuery: "",
            productResults: [],
            sendingProductId: false,
            removingCartLineId: false,
            checkingOut: false,
            // El catálogo es lo que más se usa para mandar algo por
            // WhatsApp; el resto arranca plegado para que no haga falta
            // scrollear un montón cuando hay actividades/presupuestos/
            // facturas recientes antes -eso es justo lo que se quejó el
            // usuario ("productos me manda muy abajo").
            collapsed: this._getStoredCollapsedState(),
        });

        onWillStart(() => this._load(this.props.channelId));
        onWillUpdateProps((nextProps) => {
            if (nextProps.channelId !== this.props.channelId) {
                return this._load(nextProps.channelId);
            }
        });

        // Los accesos que abren en una pestaña nueva (ver más abajo)
        // pueden crear/editar registros que cambian los contadores del
        // panel (una Oportunidad nueva, una Factura confirmada...); al
        // volver a esta pestaña se refresca solo, sin tener que cerrar
        // el chat para verlo actualizado.
        this._onWindowFocus = () => this._reload();
        onMounted(() => window.addEventListener("focus", this._onWindowFocus));
        onWillUnmount(() => window.removeEventListener("focus", this._onWindowFocus));
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
        if (this.__owl__?.status === "destroyed") {
            return;
        }
        await this._load(this.props.channelId);
    }

    async openActivity(activity) {
        if (!activity || !activity.id) {
            return;
        }
        try {
            const action = await this.orm.call(
                "chatroom.channel", "action_open_activity_form",
                [this.props.channelId, activity.id]);
            this._openDialog(action);
        } catch (error) {
            this.notification.add(error.data ? error.data.message : error.message, {
                type: "danger",
            });
        }
    }

    async scheduleActivity() {
        try {
            const action = await this.orm.call(
                "chatroom.channel", "action_open_activity_schedule",
                [this.props.channelId]);
            this._openDialog(action);
        } catch (error) {
            this.notification.add(error.data ? error.data.message : error.message, {
                type: "danger",
            });
        }
    }

    async openCalendarMeeting() {
        try {
            const action = await this.orm.call(
                "chatroom.channel", "action_open_calendar_meeting",
                [this.props.channelId]);
            this._openDialog(action);
        } catch (error) {
            this.notification.add(error.data ? error.data.message : error.message, {
                type: "danger",
            });
        }
    }

    async markActivityDone(activity) {
        if (!activity || !activity.id || this.state.completingActivityId) {
            return;
        }
        this.state.completingActivityId = activity.id;
        try {
            await this.orm.call(
                "chatroom.channel", "action_mark_next_activity_done",
                [this.props.channelId, activity.id]);
            this.notification.add("Actividad marcada como hecha.", { type: "success" });
            await this._reload();
        } catch (error) {
            this.notification.add(error.data ? error.data.message : error.message, {
                type: "danger",
            });
        } finally {
            this.state.completingActivityId = false;
        }
    }

    _getStoredCollapsedState() {
        const defaults = {
            actions: true,
            activities: true,
            opportunities: true,
            orders: true,
            invoices: true,
            cart: false,
            catalog: false,
            payments: true,
        };
        try {
            const raw = localStorage.getItem(COLLAPSED_SECTIONS_STORAGE_KEY);
            return raw ? { ...defaults, ...JSON.parse(raw) } : defaults;
        } catch {
            return defaults;
        }
    }

    toggleSection(key) {
        this.state.collapsed[key] = !this.state.collapsed[key];
        try {
            localStorage.setItem(
                COLLAPSED_SECTIONS_STORAGE_KEY, JSON.stringify(this.state.collapsed));
        } catch {
            // Sin localStorage el plegado sigue funcionando, solo no se
            // recuerda entre sesiones.
        }
    }

    onSectionHeaderKeydown(ev, key) {
        if (ev.key === "Enter" || ev.key === " ") {
            ev.preventDefault();
            this.toggleSection(key);
        }
    }

    partnerAvatarUrl() {
        if (!this.state.data || !this.state.data.partner_id) {
            return "";
        }
        // unique=write_date rompe el caché del navegador cuando se
        // sube una foto nueva -sin esto, el <img> seguía mostrando la
        // respuesta vieja cacheada aunque el campo ya hubiera cambiado.
        return imageUrl("res.partner", this.state.data.partner_id, "avatar_128", {
            unique: this.state.data.partner_write_date,
        });
    }

    formatMoney(amount, symbol) {
        const value = (amount || 0).toLocaleString(undefined, {
            minimumFractionDigits: 2, maximumFractionDigits: 2,
        });
        return symbol ? `${value} ${symbol}` : value;
    }

    // Todo lo que abre un formulario/lista de Odoo se abre como diálogo
    // (target "new") encima de la app, no navegando afuera: el pedido
    // explícito fue no perder el chat para ir a buscar Ventas/Facturas
    // a otro lado. Es el formulario real de Odoo (con sus botones
    // nativos: Confirmar, Crear factura, etc.), no una versión propia.
    openPartner() {
        if (!this.state.data || !this.state.data.partner_id) {
            return;
        }
        this._openDialog({
            type: "ir.actions.act_window",
            res_model: "res.partner",
            res_id: this.state.data.partner_id,
            views: [[false, "form"]],
        });
    }

    openRecord(resModel, resId) {
        this._openDialog({
            type: "ir.actions.act_window",
            res_model: resModel,
            res_id: resId,
            views: [[false, "form"]],
        });
    }

    async _openDialog(action) {
        if (!action || action.type !== "ir.actions.act_window") {
            this.notification.add("No se pudo abrir esta vista en el panel.", { type: "danger" });
            return;
        }
        const viewTypes = [
            ...(action.views || []).map((view) => view[1]),
            ...(action.view_mode || "").split(","),
        ];
        const isMultiRecordAction = viewTypes.some((viewType) =>
            ["list", "kanban", "pivot", "graph", "calendar", "activity"].includes(viewType)
        );
        const options = isMultiRecordAction ? {} : { onClose: () => this._reload() };
        try {
            await this.action.doAction({ ...action, target: "new" }, options);
        } catch (error) {
            this.notification.add(error.data ? error.data.message : error.message, { type: "danger" });
        }
    }

    // Odoo no deja cambiar de vista (lista -> form) DENTRO de un diálogo
    // (target "new"): el propio framework bloquea el switchView mientras
    // haya un diálogo abierto, así que ni haciendo clic en una fila se
    // podía abrir su formulario -no era un botón roto, es una limitación
    // real del framework con acciones multi-vista en diálogo. Para las
    // que necesitan navegar entre varios registros (lista/kanban/form)
    // se abren en una pestaña nueva -Odoo completo, con todo (kanban con
    // arrastrar y soltar, filtros, acciones en lote), sin perder el chat
    // en la pestaña original.
    async _openChannelAction(methodName) {
        try {
            const result = await this.orm.call(
                "chatroom.channel", methodName, [this.props.channelId]);
        // Mantener las acciones multi-vista como popup nativo. El parche de
        // embedded_record_open.js permite cambiar lista/kanban y abrir el
        // formulario sin salir de este popup.
            await this._openDialog(result);
        } catch (error) {
            this.notification.add(error.data ? error.data.message : error.message, {
                type: "danger",
            });
        }
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

    createLead() {
        this._openChannelAction("action_create_lead");
    }

    createQuotation() {
        this._openChannelAction("action_create_quotation");
    }

    createInvoice() {
        this._openChannelAction("action_create_invoice");
    }

    createPurchase() {
        this._openChannelAction("action_create_purchase_order");
    }

    createTask() {
        this._openChannelAction("action_create_task");
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

    async copyPaymentLink(link) {
        if (!link) {
            return;
        }
        try {
            await navigator.clipboard.writeText(link);
            this.notification.add("Enlace copiado al portapapeles.", { type: "success" });
        } catch {
            this.notification.add("No se pudo copiar el enlace.", { type: "warning" });
        }
    }

    productImageUrl(product) {
        return `/web/image/product.product/${product.id}/image_128`;
    }

    async openProductCatalog() {
        const result = await this.orm.call("chatroom.channel", "action_view_products", []);
        this._openDialog(result);
    }

    // ------------------------------------------------------------------
    // Carrito armado por la IA (o a mano): ver, sacar líneas, y pasarlo a
    // una Cotización real cuando está listo. La IA nunca la confirma
    // sola -- esto abre el formulario real de Odoo para que un agente lo
    // revise antes de mandarlo a producción.
    // ------------------------------------------------------------------
    async removeCartLine(lineId) {
        if (this.state.removingCartLineId) {
            return;
        }
        this.state.removingCartLineId = lineId;
        try {
            await this.orm.call(
                "chatroom.channel", "action_remove_cart_line", [this.props.channelId, lineId]);
            await this._reload();
        } catch (error) {
            this.notification.add(error.data ? error.data.message : error.message, {
                type: "danger",
            });
        } finally {
            this.state.removingCartLineId = false;
        }
    }

    async checkoutCart() {
        if (this.state.checkingOut) {
            return;
        }
        this.state.checkingOut = true;
        try {
            const orderId = await this.orm.call(
                "chatroom.channel", "action_checkout_cart", [this.props.channelId]);
            await this._reload();
            this.openRecord("sale.order", orderId);
        } catch (error) {
            this.notification.add(error.data ? error.data.message : error.message, {
                type: "danger",
            });
        } finally {
            this.state.checkingOut = false;
        }
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

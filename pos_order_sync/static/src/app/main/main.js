/* Copyright (c) 2016-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>) */
/* See LICENSE file for full copyright and licensing details. */
/* License URL : <https://store.webkul.com/license.html/> */

import { PosStore } from "@point_of_sale/app/services/pos_store";
import { Navbar } from "@point_of_sale/app/components/navbar/navbar";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { ReceiptScreen } from "@point_of_sale/app/screens/receipt_screen/receipt_screen";
import { Component, onMounted } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { patch } from "@web/core/utils/patch";
import { Dialog } from "@web/core/dialog/dialog";
import { PosOrder } from "@point_of_sale/app/models/pos_order";

// ============================================================
// PosStore patch
// ============================================================

patch(PosOrder.prototype, {
    setup() {
        super.setup(...arguments);
        //console.log("Pos Order Sync - Order setup patched");
        this.quote_id = this.quote_id || false;
        this.quote_name = this.quote_name || "";
        this.seller_name = this.seller_name || "";
        this.cashier_name = this.cashier_name || "";
    },

    // Compatibility helpers for the original addon code. Odoo 19 renamed
    // these public POS model methods to camelCase.
    get_partner() {
        return this.getPartner();
    },
    set_partner(partner) {
        return this.setPartner(partner);
    },
    get_orderlines() {
        return this.getOrderlines();
    },
    get_total_with_tax() {
        return this.priceIncl;
    },
    get_total_tax() {
        return this.prices.taxDetails.tax_amount_currency;
    },
});


patch(PosStore.prototype, {
    async setup(...args) {
        await super.setup(...args);
        this.all_quotes = Array.isArray(this.all_quotes) ? this.all_quotes : [];
        this._quotePollingTimer = null;
        this._quotePollingBusy = false;
        this._startQuotePolling();
    },

    get orders() {
        return this.models?.["pos.order"]?.getAll() || [];
    },
    get_order() {
        return this.getOrder();
    },
    add_new_order(data = {}) {
        return this.addNewOrder(data);
    },
    showScreen(routeName, params = {}) {
        return this.navigate(routeName, params);
    },

    async processServerData() {
        var self = this;
        await super.processServerData();
        self.all_quotes = Array.isArray(self.all_quotes) ? self.all_quotes : [];
        const pos_sessions = await self.env.services.orm.searchRead(
            "pos.session",
            [["state", "=", "opened"], ["id", "!=", odoo.pos_session_id]]
        );
        var other_active_session = Array.isArray(pos_sessions) ? pos_sessions : [];
        var config_list = other_active_session
            .map((el) => el.config_id?.[0])
            .filter(Boolean);
        self.other_config_ids = [...new Set(config_list)];
        self.other_active_session = other_active_session;
        if (self.other_active_session) {
            const floors = await self.env.services.orm.silent.call(
                "pos.config",
                "get_floors",
                [{ config: self.config.id, other_config: self.other_config_ids }]
            );
            if (floors) {
                self.other_floors = floors;
                self.other_floor_ids = [];
                self.floors_by_id = [];
                if (self.other_floors) {
                    for (var i = 0; i < self.other_floors.length; i++) {
                        self.other_floor_ids.push(self.other_floors[i].id);
                        self.floors_by_id[self.other_floors[i].id] = self.other_floors[i];
                    }
                }
            }
        }
    },

    _updateQuoteIndicator() {
        const quotes = Array.isArray(this.all_quotes) ? this.all_quotes : [];
        const count = quotes.filter((quote) => !quote.loaded).length;
        const indicator = document.getElementById("new_quote_notification");
        const counter = document.querySelector("#new_quote_notification .quotation_count");
        if (counter) counter.textContent = count ? String(count) : "";
        if (indicator) {
            indicator.style.color = count ? "rgb(79, 207, 228)" : "rgb(58, 133, 141)";
            indicator.title = count
                ? `${count} pedido(s) recibido(s). Abrir pedidos recibidos`
                : "No hay pedidos recibidos";
            indicator.setAttribute("aria-label", indicator.title);
        }
    },

    markQuoteLoaded(quoteId) {
        const quote = (this.all_quotes || []).find((item) => item.quote_id === quoteId);
        if (quote) quote.loaded = true;
        this._updateQuoteIndicator();
    },

    async refreshIncomingQuotes(showNotification = false) {
        if (this._quotePollingBusy || !this.session?.id) return [];
        this._quotePollingBusy = true;
        try {
            const knownQuotes = Array.isArray(this.all_quotes) ? this.all_quotes : [];
            const knownIds = new Set(knownQuotes.map((quote) => quote.quote_id).filter(Boolean));
            const result = await this.env.services.orm.silent.call(
                "pos.quote",
                "search_all_record",
                [{
                    quote_ids: [...knownIds],
                    session_id: this.session.id,
                }]
            );
            const incoming = (Array.isArray(result?.quote_list) ? result.quote_list : [])
                .filter((quote) => quote && quote.quote_id)
                .map((quote) => ({
                    ...quote,
                    quote_id: String(quote.quote_id),
                    from_session_id: quote.from_session_id || "Otra caja",
                    partner_id: Array.isArray(quote.partner_id) ? quote.partner_id : [false, "-"],
                    line: Array.isArray(quote.line) ? quote.line : [],
                    amount_total: Number(quote.amount_total) || 0,
                    loaded: Boolean(quote.loaded),
                }));
            const fresh = incoming.filter((quote) => !knownIds.has(quote.quote_id));
            if (fresh.length) {
                this.all_quotes = [...fresh, ...knownQuotes];
                if (showNotification && this.notification) {
                    const message = fresh.length === 1
                        ? `Nuevo pedido recibido desde ${fresh[0].from_session_id || "otra caja"}.`
                        : `${fresh.length} pedidos nuevos recibidos.`;
                    this.notification.add(message, { type: "info", title: "Pedido entre cajas" });
                }
            }
            this._updateQuoteIndicator();
            return fresh;
        } catch (error) {
            console.warn("No se pudieron consultar pedidos recibidos:", error);
            return [];
        } finally {
            this._quotePollingBusy = false;
        }
    },

    _startQuotePolling() {
        if (this._quotePollingTimer) return;
        this.refreshIncomingQuotes(false);
        this._quotePollingTimer = window.setInterval(
            () => this.refreshIncomingQuotes(true),
            5000
        );
    },

    getSyncAllOrdersContext(orders, options = {}) {
        var self = this;
        var data = super.getSyncAllOrdersContext(...arguments);
        const order = self.get_order();
        $("#quote_history").css("color", "rgb(94, 185, 55)");
        if (order && order.quote_id) {
            self.env.services.orm.write("pos.quote", [order.quote_id], { state: "done" });
            var quote_list = [];
            var result_list_length;
            var all_quotes = Array.isArray(self.all_quotes) ? self.all_quotes : [];
            var session_id = self.session.id;
            all_quotes.forEach(function (quote) {
                if (quote.quote_obj_id === order.quote_id) {
                    quote.state = "done";
                }
                if (quote.quote_obj_id !== order.quote_id) {
                    quote_list.push(quote.quote_id);
                }
            });
            setTimeout(async function () {
                const result_all_record = await self.env.services.orm.silent.call(
                    "pos.quote",
                    "search_all_record",
                    [
                        {
                            quote_ids: quote_list,
                            session_id: session_id,
                        },
                    ]
                );
                if (result_all_record) {
                    result_list_length = result_all_record.quote_list;
                    if (result_list_length) $("#new_quote_notification").css("color", "rgb(79, 207, 228)");
                    else $("#new_quote_notification").css("color", "rgb(58, 133, 141)");
                    $(".quotation_count").text(result_list_length.length);
                }
            }, 150);
        }
        return data;
    },
});

// ============================================================
// ReceiptScreen patch
// ============================================================
patch(ReceiptScreen.prototype, {
    setup() {
        this.pos = usePos();
        super.setup();
        onMounted(this.WkOnMounted);
    },
    WkOnMounted() {
        var self = this;
        var all_quotes = (Array.isArray(self.pos.all_quotes) ? self.pos.all_quotes : [])
            .filter((quote) => !quote.loaded);
        var index = null;
        var current_order = self.pos.get_order();
        if (current_order?.quote_name) {
            for (var i = 0; i < all_quotes.length; i++) {
                if (all_quotes[i].quote_id == current_order.quote_name) {
                    index = i;
                    break;
                }
            }
        }
        if (index != null) all_quotes.splice(index, 1);
        self.pos.all_quotes = all_quotes;
        if (all_quotes.length == 0) $("#new_quote_notification").css("color", "rgb(58, 133, 141)");
    },
});

// ============================================================
// Navbar patch (FIX COMPLETO PARTNER + PRODUCTOS + AWAITS)
// ============================================================
patch(Navbar.prototype, {
    setup() {
        this.dialog = useService("dialog");
        this.pos = usePos();
        super.setup();
        onMounted(this.WkOnMounted);
    },

    WkOnMounted() {
        $("#new_quote_notification").css("color", "rgb(58, 133, 141)");
    },

    // ============================================================
    // ✅ Helpers Productos (completos)
    // ============================================================
    _normalizeM2O(raw) {
        if (Array.isArray(raw)) return raw[0] || null;
        const n = parseInt(raw || 0);
        return n || null;
    },

    _tryInsertRecords(Model, recs) {
        try {
            if (!Model || !recs || !recs.length) return false;

            if (Model.addRecords) {
                Model.addRecords(recs);
                return true;
            }
            if (Model.loadData) {
                Model.loadData(recs);
                return true;
            }

            if (Model.insert) {
                recs.forEach((r) => Model.insert(r));
                return true;
            }
            if (Model.add) {
                recs.forEach((r) => Model.add(r));
                return true;
            }
            if (Model.create) {
                recs.forEach((r) => Model.create(r));
                return true;
            }

            return false;
        } catch (e) {
            console.warn("No pude insertar records al store:", e);
            return false;
        }
    },

    async _loadProductsForPos(productIds) {
        try {
            const ProductModel = this.pos.models["product.product"];
            const ids = [...new Set((productIds || []).filter(Boolean))];
            if (!ids.length) return;

            const missing = ids.filter((id) => !ProductModel?.get(id));
            if (!missing.length) return;

            // Odoo 19 related models must be loaded through PosData so their
            // relations and IndexedDB state are initialized correctly.
            await this.pos.data.callRelated(
                "pos.config",
                "load_products_for_pos",
                [{ config_id: this.pos.config.id, product_ids: missing }],
                {},
                false,
                true
            );
            if (missing.every((id) => ProductModel?.get(id))) return;

            console.group("🧩 POS | _loadProductsForPos (Navbar)");
            console.log("Missing ids:", missing);

            const fields = [
                "id",
                "display_name",
                "name",
                "categ_id",
                "lst_price",
                "barcode",
                "default_code",
                "uom_id",
                "taxes_id",
                "available_in_pos",
                "sale_ok",
            ];

            const recs = await this.env.services.orm.searchRead("product.product", [["id", "in", missing]], fields);
            console.log("Fetched products:", recs?.length || 0);

            if (!recs?.length) {
                console.warn("❌ No products returned from server.");
                console.groupEnd();
                return;
            }

            const inserted = this._tryInsertRecords(ProductModel, recs);
            console.log("Inserted into store:", inserted);

            const stillMissing = missing.filter((id) => !ProductModel?.get(id));
            if (stillMissing.length) console.warn("❌ Still missing after insert:", stillMissing);
            else console.log("✅ Products now in cache");

            console.groupEnd();
        } catch (e) {
            console.warn("_loadProductsForPos error:", e);
        }
    },

    // ============================================================
    // ✅ Helper robusto Partner
    // ============================================================
    async _loadPartnerForPos(partnerId) {
        try {
            const PartnerModel = this.pos.models["res.partner"];
            let partner = PartnerModel?.get(partnerId);
            if (partner) return partner;

            await this.pos.data.callRelated(
                "res.partner",
                "get_new_partner",
                [this.pos.config.id, [["id", "=", partnerId]], 0],
                {},
                false,
                true
            );
            partner = PartnerModel?.get(partnerId);
            if (partner) return partner;

            const recs = await this.env.services.orm.read("res.partner", [partnerId], [
                "name",
                "vat",
                "email",
                "phone",
                "mobile",
                "street",
                "street2",
                "city",
                "zip",
                "country_id",
                "state_id",
                "property_product_pricelist",
                "company_type",
            ]);

            if (!recs?.length) return null;

            try {
                if (PartnerModel.addRecords) PartnerModel.addRecords(recs);
                else if (PartnerModel.loadData) PartnerModel.loadData(recs);
                else if (PartnerModel.insert) PartnerModel.insert(recs[0]);
                else if (PartnerModel.add) PartnerModel.add(recs[0]);
                else if (PartnerModel.create) PartnerModel.create(recs[0]);
            } catch (e) {
                console.warn("No pude insertar partner al store:", e);
            }

            partner = PartnerModel?.get(partnerId);
            return partner || null;
        } catch (e) {
            console.warn("_loadPartnerForPos error:", e);
            return null;
        }
    },

    async click_quote_history(event) {
        var self = this;
        try {
            const result = await self.env.services.orm.silent.call("pos.quote", "load_quote_history", [
                {
                    session_id: self.pos.session.id,
                },
            ]);
            if (result) {
                self.pos.history = result.quote_list;
                $("#quote_history").css("color", "rgb(94, 185, 55)");
                self.dialog.add(QuoteHistoryPopupWidget, {
                    qoutes: self.pos.history,
                });
            }
        } catch {
            $("#quote_history").css("color", "red");
            self.dialog.add(WkErrorNotifyPopopWidget, {
                title: "No se pudo mostrar el historial",
                body: "Verifica la conexión de red e inténtalo nuevamente.",
            });
        }
    },

    async click_save_order_quote(event) {
        var self = this;
        var current_order = self.pos.get_order();
        if (current_order && current_order.get_orderlines()) {
            if (current_order.get_orderlines().length == 0)
                self.dialog.add(WkErrorNotifyPopopWidget, {
                    title: "Pedido vacío",
                    body: "No puedes enviar un pedido vacío. Agrega al menos un producto al carrito.",
                });
            else {
                try {
                    const quote_sequence_id = await self.env.services.orm.silent.call("ir.sequence", "next_by_code", [
                        "pos.quote",
                    ]);
                    if (quote_sequence_id) {
                        self.dialog.add(SaveAsOrderQuotePopupWidget, {});
                        setTimeout(function () {
                            $("#quote_note").focus();
                            $("#quote_id").text(quote_sequence_id);
                        }, 150);
                    }
                } catch {
                    self.dialog.add(WkErrorNotifyPopopWidget, {
                        title: "No se pudo preparar el envío",
                        body: "Verifica la conexión de red e inténtalo nuevamente.",
                    });
                }
            }
        }
    },

    async click_new_quote_notification() {
        var self = this;
        $(".wk_loading").show();
        await self.pos.refreshIncomingQuotes(false);
        $(".wk_loading").hide();
        $(".quotation_count").show();
        $(".fa-shopping-cart").show();

        var all_quotes = (Array.isArray(self.pos.all_quotes) ? self.pos.all_quotes : [])
            .filter((quote) => quote && !quote.loaded);
        var all_quotes_length = all_quotes.length;
        self.pos._updateQuoteIndicator();

        if (all_quotes_length == 0) {
            $("#order_quote_notification").text("No hay pedidos recibidos");
            $("#order_quote_notification").fadeIn();
            setTimeout(function () {
                $("#order_quote_notification").fadeOut();
            }, 2000);
        } else if (all_quotes_length == 1) {
                var all_pos_orders = self.pos.orders || [];
                let already_loaded = false;

                already_loaded = all_pos_orders.find(function (pos_order) {
                    return pos_order.quote_name && pos_order.quote_name == all_quotes[0].quote_id;
                });
                if (already_loaded) {
                    self.dialog.add(MyMessagePopup, {
                        title: "Pedido ya cargado",
                        body:
                            "Este pedido ya está cargado. Continúe con la referencia " +
                            already_loaded.sequence_number,
                    });
                    return;
                }

                var quote_dict = all_quotes[0];
                self.pos.add_new_order();
                var temp = await self.check_to_load(quote_dict);
                if (temp) {
                    await self.set_order(quote_dict);
                }
        } else {
            if ($(".floor-screen.screen").is(":visible")) {
                self.pos.showScreen("AllQuotesListScreenWidget");
            } else {
                self.pos.showScreen("AllQuotesListScreenWidget");
            }
        }
    },

    // ============================================================
    // ✅ check_to_load: precarga productos faltantes si hay restricción
    // ============================================================
    async check_to_load(quote_dict) {
        var self = this;

        if (self.pos.config.iface_available_categ_ids.length === 0) {
            return true;
        }

        const productIds = (quote_dict.line || [])
            .map((l) => self._normalizeM2O(l.product_id))
            .filter(Boolean);

        await self._loadProductsForPos(productIds);

        const ProductModel = self.pos.models["product.product"];
        const missing = productIds.filter((id) => !ProductModel?.get(id));

        if (missing.length) {
            console.warn("⚠️ Products still missing in POS cache (Navbar):", missing);
            // Si deseas bloquear: return false y habilitar ConfirmationDialog.
            return true;
        }

        return true;
    },

    // ============================================================
    // ✅ set_order: FIX real para productos faltantes
    // ============================================================
    async set_order(quote_dict) {
        var self = this;

        await self.dialog.add(QuoteSendPopupWidget, {
            quote_status: "Pedido recibido: listo para revisar",
        });

        var new_order = self.pos.get_order();
        console.log("quote_dict =", quote_dict);

        // 1) Partner
        const partnerId = quote_dict?.partner_id?.[0] || null;
        if (partnerId) {
            const partnerObj = await self._loadPartnerForPos(partnerId);
            new_order.set_partner(partnerObj ?? null);
        } else {
            new_order.set_partner(null);
        }

        // 2) Precargar productos si hay restricción
        const productIds = (quote_dict.line || [])
            .map((l) => self._normalizeM2O(l.product_id))
            .filter(Boolean);

        if (self.pos.config.iface_available_categ_ids.length) {
            await self._loadProductsForPos(productIds);
        }

        const ProductModel = self.pos.models["product.product"];

        // 3) Líneas
        for (const line of quote_dict.line || []) {
            const productId = self._normalizeM2O(line.product_id);
            const product = productId ? ProductModel.get(productId) : undefined;

            console.log("line.product_id =", line.product_id, " normalized =", productId, " product =", product);

            // ✅ condición correcta
            if (self.pos.config.iface_available_categ_ids.length === 0 || product !== undefined) {
                let sale_order_origin_id = false;
                if (line.sale_order_origin_id?.[0] && self.pos._getSaleOrder) {
                    sale_order_origin_id = await self.pos._getSaleOrder(line.sale_order_origin_id[0]);
                }

                await self.pos.addLineToCurrentOrder({
                    product_id: product,
                    price_unit: line.price_unit,
                    qty: line.qty,
                    so_reference: line.so_reference,
                    sale_order_origin_id: sale_order_origin_id,
                });
            } else {
                console.warn("❌ Skipping line, product still undefined (Navbar):", { productId, line });
            }
        }

        // 4) Extras
        new_order.quote_id = quote_dict.quote_obj_id || false;
        new_order.quote_name = quote_dict.quote_id || "";
        new_order.seller_name = quote_dict.seller_name || "";
        new_order.cashier_name = self.pos.cashier?.name || self.pos.user?.name || "";
        new_order.setInternalNote(quote_dict.note || "");
        if (quote_dict.quote_obj_id) {
            const cashier = self.pos.cashier;
            const cashierUserId = cashier?.model?.name === "res.users"
                ? cashier.id
                : cashier?.user_id?.id || false;
            await self.env.services.orm.silent.call("pos.quote", "mark_received", [
                quote_dict.quote_obj_id,
                cashierUserId,
                cashier?.name || self.pos.user?.name || "",
            ]);
        }
        self.pos.markQuoteLoaded(quote_dict.quote_id);
        //new_order.quote_name = quote_dict.quote_id || "";

        console.log("new_order.seller_name =", new_order.seller_name);
        console.log("new_order =", new_order);
        console.log('quote name', new_order.quote_name);
        return new_order;
    },

    async update_new_quote_list() {
        return this.pos.refreshIncomingQuotes(false);
    },
});

// ============================================================
// Components / Screens
// ============================================================
export class QuoteHistoryPopupWidget extends Component {
    static template = "pos_order_sync.QuoteHistoryPopupWidget";
    static components = { Dialog };
    static props = {
        close: Function,
        qoutes: { type: Array, optional: true },
    };
}

export class MyMessagePopup extends Component {
    static template = "pos_order_sync.MyMessagePopup";
    static components = { Dialog };
    static props = {
        close: Function,
        title: { type: String, optional: true },
        body: { type: String, optional: true },
    };
}

export class QuoteSendPopupWidget extends Component {
    static template = "pos_order_sync.QuoteSendPopupWidget";
    static components = { Dialog };

    static props = {
        close: { type: Function, optional: true },
        quote_status: { type: String, optional: true },
        clear_order: { type: Boolean, optional: true },
    };

    setup() {
        this.dialog = useService("dialog");
        this.pos = usePos();
        super.setup();
        onMounted(this.WkOnMounted);
    }

    WkOnMounted() {
        var self = this;
        $(".order_status").show();
        $("#order_sent_status").hide();
        $(".order_status").removeClass("order_done");
        $(".show_tick").hide();
        setTimeout(function () {
            $(".order_status").addClass("order_done");
            $(".show_tick").show();
            $("#order_sent_status").show();
            $(".order_status").css({ "border-color": "#5cb85c" });
        }, 500);

        const shouldClearOrder = Boolean(
            self.props?.clear_order || !self.props?.quote_status
        );
        if (shouldClearOrder) {
            const orderToRemove = self.pos.get_order();
            setTimeout(function () {
                if (orderToRemove) {
                    self.pos.removeOrder(orderToRemove, false);
                }
                self.props.close?.();
                self.pos.add_new_order();
            }, 1500);
        } else {
            setTimeout(function () {
                self.props.close?.();
            }, 1500);
        }
    }
}

export class WkErrorNotifyPopopWidget extends Component {
    static template = "pos_order_sync.WkErrorNotifyPopopWidget";
    static components = { Dialog };
    static props = {
        close: Function,
        title: { type: String, optional: true },
        body: { type: String, optional: true },
    };
}

export class WkQuoteLine extends Component {
    static template = "pos_order_sync.WkQuoteLine";
}

// ============================================================
// AllQuotesListScreenWidget (100% FIX productos + partner + awaits)
// ============================================================
export class AllQuotesListScreenWidget extends Component {
    static template = "pos_order_sync.AllQuotesListScreenWidget";
    static components = { WkQuoteLine };

    setup() {
        this.dialog = useService("dialog");
        this.pos = usePos();
        super.setup();
    }

    // ===== Helpers (duplicados aquí para que quede 100% sólido) =====
    _normalizeM2O(raw) {
        if (Array.isArray(raw)) return raw[0] || null;
        const n = parseInt(raw || 0);
        return n || null;
    }

    _tryInsertRecords(Model, recs) {
        try {
            if (!Model || !recs || !recs.length) return false;

            if (Model.addRecords) {
                Model.addRecords(recs);
                return true;
            }
            if (Model.loadData) {
                Model.loadData(recs);
                return true;
            }

            if (Model.insert) {
                recs.forEach((r) => Model.insert(r));
                return true;
            }
            if (Model.add) {
                recs.forEach((r) => Model.add(r));
                return true;
            }
            if (Model.create) {
                recs.forEach((r) => Model.create(r));
                return true;
            }

            return false;
        } catch (e) {
            console.warn("No pude insertar records al store:", e);
            return false;
        }
    }

    async _loadProductsForPos(productIds) {
        try {
            const ProductModel = this.pos.models["product.product"];
            const ids = [...new Set((productIds || []).filter(Boolean))];
            if (!ids.length) return;

            const missing = ids.filter((id) => !ProductModel?.get(id));
            if (!missing.length) return;

            await this.pos.data.callRelated(
                "pos.config",
                "load_products_for_pos",
                [{ config_id: this.pos.config.id, product_ids: missing }],
                {},
                false,
                true
            );
            if (missing.every((id) => ProductModel?.get(id))) return;

            console.group("🧩 POS | _loadProductsForPos (Screen)");
            console.log("Missing ids:", missing);

            const fields = [
                "id",
                "display_name",
                "name",
                "categ_id",
                "lst_price",
                "barcode",
                "default_code",
                "uom_id",
                "taxes_id",
                "available_in_pos",
                "sale_ok",
            ];

            const recs = await this.env.services.orm.searchRead("product.product", [["id", "in", missing]], fields);
            console.log("Fetched products:", recs?.length || 0);

            if (!recs?.length) {
                console.warn("❌ No products returned from server.");
                console.groupEnd();
                return;
            }

            const inserted = this._tryInsertRecords(ProductModel, recs);
            console.log("Inserted into store:", inserted);

            const stillMissing = missing.filter((id) => !ProductModel?.get(id));
            if (stillMissing.length) console.warn("❌ Still missing after insert:", stillMissing);
            else console.log("✅ Products now in cache");

            console.groupEnd();
        } catch (e) {
            console.warn("_loadProductsForPos (screen) error:", e);
        }
    }

    async _loadPartnerForPos(partnerId) {
        try {
            const PartnerModel = this.pos.models["res.partner"];
            let partner = PartnerModel?.get(partnerId);
            if (partner) return partner;

            await this.pos.data.callRelated(
                "res.partner",
                "get_new_partner",
                [this.pos.config.id, [["id", "=", partnerId]], 0],
                {},
                false,
                true
            );
            partner = PartnerModel?.get(partnerId);
            if (partner) return partner;

            const recs = await this.env.services.orm.read("res.partner", [partnerId], [
                "name",
                "vat",
                "email",
                "phone",
                "mobile",
                "street",
                "street2",
                "city",
                "zip",
                "country_id",
                "state_id",
                "property_product_pricelist",
                "company_type",
            ]);

            if (!recs?.length) return null;

            try {
                if (PartnerModel.addRecords) PartnerModel.addRecords(recs);
                else if (PartnerModel.loadData) PartnerModel.loadData(recs);
                else if (PartnerModel.insert) PartnerModel.insert(recs[0]);
                else if (PartnerModel.add) PartnerModel.add(recs[0]);
                else if (PartnerModel.create) PartnerModel.create(recs[0]);
            } catch (e) {
                console.warn("No pude insertar partner al store:", e);
            }

            partner = PartnerModel?.get(partnerId);
            return partner || null;
        } catch (e) {
            console.warn("_loadPartnerForPos (screen) error:", e);
            return null;
        }
    }

    async qoute_line(quote_id) {
        var self = this;
        var quotes = Array.isArray(self.pos.all_quotes) ? self.pos.all_quotes : [];
        var clicked_quote_id = quote_id;
        var quote_dict;
        quotes.forEach(function (quote) {
            if (quote.quote_id == clicked_quote_id) {
                quote_dict = quote;
            }
        });

        if (!quote_dict) {
            self.dialog.add(MyMessagePopup, {
                title: "Pedido no disponible",
                body: "El pedido ya fue cargado o ya no está disponible.",
            });
            return;
        }

        let already_loaded = false;
        var all_pos_orders = self.pos.orders || [];
        already_loaded = all_pos_orders.find(function (pos_order) {
            return pos_order.quote_name && pos_order.quote_name == quote_dict.quote_id;
        });

        if (already_loaded) {
            self.dialog.add(MyMessagePopup, {
                title: "El pedido ya está cargado",
                body:
                    "Este pedido ya está abierto. Continúa con la referencia " +
                    already_loaded.sequence_number,
            });
            return;
        } else {
            var set = false;

            if (self.pos.config.module_pos_restaurant && self.pos.config.floor_ids) {
                if (quote_dict.table_json) {
                    var table_data = JSON.parse(quote_dict.table_json);
                    if (table_data) {
                        var table_id = table_data.table_json[0].table_id;
                        var floor_id = table_data.table_json[1].floor_id;
                        const floor = await self.env.services.orm.searchRead("restaurant.floor", [["id", "=", floor_id]], []);
                        if (floor_id && table_id) {
                            if (floor) {
                                floor.table_ids.forEach(async function (id) {
                                    if (id == table_id) {
                                        set = true;
                                        const table = await self.env.services.orm.searchRead("restaurant.table", [["id", "=", id]], []);
                                        self.pos.setTable(table);
                                        self.pos.add_new_order();
                                        if (set) {
                                            self.pos.showScreen("ProductScreen");
                                            var temp = await self.check_to_load(quote_dict);
                                            if (temp) {
                                                await self.set_order(quote_dict);
                                            } else {
                                                self.pos.showScreen("ProductScreen");
                                            }
                                        }
                                        $(".button.back").click();
                                    }
                                });
                            }
                        }
                    }
                }
            }

            if (!set) {
                self.pos.add_new_order();
                var temp = await self.check_to_load(quote_dict);
                if (temp) {
                    await self.set_order(quote_dict);
                    self.pos.showScreen("ProductScreen");
                } else {
                    self.pos.showScreen("ProductScreen");
                }
            }
        }
    }

    // ✅ check_to_load FIX (screen)
    async check_to_load(quote_dict) {
        if (this.pos.config.iface_available_categ_ids.length === 0) {
            return true;
        }

        const productIds = (quote_dict.line || [])
            .map((l) => this._normalizeM2O(l.product_id))
            .filter(Boolean);

        await this._loadProductsForPos(productIds);

        const ProductModel = this.pos.models["product.product"];
        const missing = productIds.filter((id) => !ProductModel?.get(id));

        if (missing.length) {
            console.warn("⚠️ Products still missing in POS cache (Screen):", missing);
            return true; // o false si quieres bloquear
        }
        return true;
    }

    click_back(event) {
        this.pos.showScreen("ProductScreen");
    }

    get quoteline() {
        var self = this;
        var all_quotations_for_customer = Array.isArray(self.pos.all_quotes)
            ? self.pos.all_quotes
            : [];
        all_quotations_for_customer = all_quotations_for_customer.filter((quote) => !quote.loaded);
        var intput_txt = $(".quotation_search").val();
        if (intput_txt != undefined && intput_txt != "") {
            var new_quotation_data = [];
            var search_text = intput_txt.toLowerCase();
            all_quotations_for_customer.forEach(function (quotation) {
                const quoteId = String(quotation.quote_id || "").toLowerCase();
                const fromSession = String(quotation.from_session_id || "").toLowerCase();
                if (quoteId.indexOf(search_text) != -1 || fromSession.indexOf(search_text) != -1) {
                    new_quotation_data = new_quotation_data.concat(quotation);
                }
            });
            all_quotations_for_customer = new_quotation_data;
        }
        return all_quotations_for_customer;
    }

    // ✅ set_order FIX (screen)
    async set_order(quote_dict) {
        var self = this;

        await self.dialog.add(QuoteSendPopupWidget, {
            quote_status: "Pedido recibido: listo para revisar",
        });

        var new_order = self.pos.get_order();
        console.log("quote_dict =", quote_dict);

        const partnerId = quote_dict?.partner_id?.[0] || null;
        if (partnerId) {
            const partnerObj = await self._loadPartnerForPos(partnerId);
            new_order.set_partner(partnerObj ?? null);
        } else {
            new_order.set_partner(null);
        }

        const productIds = (quote_dict.line || [])
            .map((l) => this._normalizeM2O(l.product_id))
            .filter(Boolean);

        if (this.pos.config.iface_available_categ_ids.length) {
            await this._loadProductsForPos(productIds);
        }

        const ProductModel = this.pos.models["product.product"];

        for (const line of quote_dict.line || []) {
            const productId = this._normalizeM2O(line.product_id);
            const product = productId ? ProductModel.get(productId) : undefined;

            console.log("line.product_id =", line.product_id, " normalized =", productId, " product =", product);

            if (this.pos.config.iface_available_categ_ids.length === 0 || product !== undefined) {
                let sale_order_origin_id = false;
                if (line.sale_order_origin_id?.[0] && self.pos._getSaleOrder) {
                    sale_order_origin_id = await this.pos._getSaleOrder(line.sale_order_origin_id[0]);
                }

                await this.pos.addLineToCurrentOrder({
                    product_id: product,
                    price_unit: line.price_unit,
                    qty: line.qty,
                    so_reference: line.so_reference,
                    sale_order_origin_id: sale_order_origin_id,
                });
            } else {
                console.warn("❌ Skipping line, product still undefined (Screen):", { productId, line });
            }
        }

        new_order.quote_id = quote_dict.quote_obj_id || false;
        new_order.quote_name = quote_dict.quote_id || "";
        new_order.seller_name = quote_dict.seller_name || "";
        new_order.cashier_name = self.pos.cashier?.name || self.pos.user?.name || "";
        new_order.setInternalNote(quote_dict.note || "");
        if (quote_dict.quote_obj_id) {
            const cashier = self.pos.cashier;
            const cashierUserId = cashier?.model?.name === "res.users"
                ? cashier.id
                : cashier?.user_id?.id || false;
            await self.env.services.orm.silent.call("pos.quote", "mark_received", [
                quote_dict.quote_obj_id,
                cashierUserId,
                cashier?.name || self.pos.user?.name || "",
            ]);
        }
        self.pos.markQuoteLoaded(quote_dict.quote_id);

        console.log("new_order.seller_name =", new_order.seller_name);
        console.log("new_order =", new_order);
        console.log('quote name', new_order.quote_name);
        return new_order;
    }
}

registry.category("pos_pages").add("AllQuotesListScreenWidget", {
    name: "AllQuotesListScreenWidget",
    component: AllQuotesListScreenWidget,
    route: `/pos/ui/${odoo.pos_config_id}/quotes`,
    params: {},
});

// ============================================================
// SaveAsOrderQuotePopupWidget (tal cual lo pegaste)
// ============================================================
export class SaveAsOrderQuotePopupWidget extends Component {
    static template = "pos_order_sync.SaveAsOrderQuotePopupWidget";
    static components = { Dialog };
    static props = { close: Function };
    setup() {
        this.dialog = useService("dialog");
        this.pos = usePos();
        this.report = useService("report");
        super.setup();
        var self = this;
        self.selected_session_id = null;
    }

    async change_tables(event) {
        var self = this;
        var related_tables = [];
        var floor_id = $("#wk_change_floor").val();
        var floor = self.pos.floors_by_id[floor_id];
        $("#wk_change_table option").remove();
        $(".show_info").hide();
        const tables = await self.env.services.orm.silent.call("pos.config", "get_tables", [
            {
                config: self.pos.config.id,
                other_config: self.pos.other_config_ids,
            },
        ]);
        if (tables) {
            self.pos.tables_by_id = tables;
            if (floor) {
                floor.table_ids.forEach(async function (table) {
                    tables.forEach(async function (tables_by_id) {
                        if (table === tables_by_id.id) {
                            related_tables.push(tables_by_id);
                        }
                    });
                });
            }
            if (related_tables.length) {
                $("#wk_change_table").append("<option value=''> </option>");
                related_tables.forEach(async function (table) {
                    $("#wk_change_table").append("<option value=" + table.id + "> " + table.name + "</option>");
                });
            }
        }
    }

    click_table(event) {
        $(".show_info").hide();
    }

    click_select_session(session_id) {
        var self = this;
        $("#wk_change_floor option").remove();
        $("#wk_change_table option").remove();
        $("#order_quote_id_input_error").hide();
        $(".show_info").hide();
        $(".select_session").css("background", "white");
        self.selected_session_id = session_id;

        if (self.selected_session_id) {
            var config_id = null;
            self.pos.other_active_session.forEach(function (other_session) {
                if (other_session.id == self.selected_session_id) {
                    config_id = other_session.config_id[0];
                }
            });

            var floors = [];
            if (self && self.pos && self.pos.other_floors) {
                self.pos.other_floors.forEach(async function (other_floor) {
                    if ((other_floor.pos_config_ids || []).includes(config_id)) {
                        floors.push(other_floor);
                    }
                });
                if (floors.length) {
                    $("#wk_floor_table").show();
                    $("#wk_change_floor option").remove();
                    $("#wk_change_table option").remove();
                    $("#wk_change_floor").append("<option value=''> </option>");
                    floors.forEach(async function (floor) {
                        if (floor.table_ids.length) {
                            $("#wk_change_floor").append("<option value=" + floor.id + "> " + floor.name + "</option>");
                        }
                    });
                } else {
                    $("#wk_floor_table").hide();
                }
            }
        }

        $("span.select_session[id=" + session_id + " ]").css("background", "#6EC89B");
    }

    async click_wk_print_and_save() {
        var self = this;
        await self.click_wk_save_order_quote(true);
        if (self.selected_session_id) {
            if (self.pos.config.quotation_print_type == "pdf" && self.pos.get_order().get_partner()) {
                await self.report.doAction("pos_order_sync.report_quote", [self.pos.get_order().created_quote_id]);
            } else if (self.pos.config.quotation_print_type == "posbox") {
                // Odoo 19 removed the legacy QWeb/proxy receipt API used by
                // the Odoo 18 addon. Use the POS printer service instead.
                await self.pos.printReceipt({ order: self.pos.get_order() });
            }
        }
    }

    async click_wk_save_order_quote(print_order_quote) {
        console.log("click_wk_save_order_quote ===========");
        var self = this;
        var current_order = self.pos.get_order();
        const currentDateTime = new Date();
        let formattedDateOrder;
        let new_quote_id;
        console.log("current_order ===========", current_order);

        const seller_name = self.pos.cashier?.name || self.pos.user?.name || "";
        current_order.seller_name = seller_name;
        
        console.log("click seller_name = ", seller_name);

        if (!current_order.get_partner()) {
            self.props.close();
            self.dialog.add(WkErrorNotifyPopopWidget, {
                title: "No se pudo guardar el pedido",
                body: "Primero selecciona un cliente.",
            });
        } else {
            var order_vals = {};
            order_vals.seller_name = seller_name;
            var session_id = self.selected_session_id;
            if (!session_id) {
                $(".select_session").css("background-color", "burlywood");
                setTimeout(function () {
                    $(".select_session").css("background-color", "");
                }, 100);
                setTimeout(function () {
                    $(".select_session").css("background-color", "burlywood");
                }, 200);
                setTimeout(function () {
                    $(".select_session").css("background-color", "");
                }, 300);
                setTimeout(function () {
                    $(".select_session").css("background-color", "burlywood");
                }, 400);
                setTimeout(function () {
                    $(".select_session").css("background-color", "");
                }, 500);
                return;
            } else {
                if ($("#wk_change_floor").val() && !$("#wk_change_table").val()) {
                    if ($("#wk_change_floor").val().length && !$("#wk_change_table").val().length) {
                        $(".show_info").show();
                        return;
                    }
                }

                order_vals.to_session_id = session_id;
                self.to_session_id = session_id;
                order_vals.user_id = self.pos.cashier ? self.pos.cashier.id : self.pos.user.id;

                if (current_order.get_partner()) {
                    order_vals.partner_id = current_order.get_partner().id;
                }
                order_vals.session_id = self.pos.session.id;
                if (current_order.pricelist_id != undefined) {
                    order_vals.pricelist_id = current_order.pricelist_id.id;
                }
                order_vals.note = $("#quote_note").val();
                order_vals.quote_id = $("#quote_id").text();
                order_vals.amount_total = current_order.get_total_with_tax();
                order_vals.amount_tax = current_order.get_total_tax();
                order_vals.trackingNumber = current_order.tracking_number;

                if (current_order) {
                    if ($("#wk_change_table").val() && $("#wk_change_floor").val()) {
                        order_vals.table_json = JSON.stringify({
                            table_json: [{ table_id: $("#wk_change_table").val() }, { floor_id: $("#wk_change_floor").val() }],
                        });
                        const floor = await self.env.services.orm.searchRead(
                            "restaurant.floor",
                            [["id", "=", parseInt($("#wk_change_floor").val())]],
                            []
                        );
                        const table = await self.env.services.orm.searchRead(
                            "restaurant.table",
                            [["id", "=", parseInt($("#wk_change_table").val())]],
                            []
                        );

                        order_vals.pos_res_info = "Floor : " + floor[0].name + " & Table : " + table[0].table_number;
                    }
                }

                order_vals.lines = [];
                var orderlines = self.pos.get_order().get_orderlines();
                orderlines.forEach(function (orderline) {
                    var order_line_vals = {};
                    order_line_vals.product_id = orderline.product_id.id;
                    order_line_vals.price_unit = orderline.price_unit;
                    order_line_vals.qty = orderline.qty;
                    order_line_vals.discount = orderline.discount;
                    order_line_vals.price_subtotal = orderline.priceExcl;
                    order_line_vals.price_subtotal_incl = orderline.priceIncl;
                    order_line_vals.so_reference = orderline.sale_order_origin_id?.name;
                    order_line_vals.sale_order_origin_id = orderline.sale_order_origin_id?.id;
                    var tax_ids = [];
                    orderline.product_id.taxes_id.forEach(function (tax_id) {
                        tax_ids.push(tax_id.id);
                    });
                    order_line_vals.quote_tax_ids = tax_ids;
                    order_vals.lines.push([0, 0, order_line_vals]);
                });

                if ($("#quote_id").text() == "") {
                    $("#order_quote_id_input_error").text("No se encontró el número del pedido.");
                    $("#order_quote_id_input_error").css("width", "66%");
                    $("#order_quote_id_input_error").css("padding-left", "26%");
                    $("#order_quote_id_input_error").show();
                } else {
                    try {
                        const result = await self.env.services.orm.silent.call("pos.quote", "search_quote", [
                            { quotation_id: $("#quote_id").text() },
                        ]);

                        if (result === undefined || result == null) {
                            try {
                                formattedDateOrder =
                                    currentDateTime.getFullYear() +
                                    "-" +
                                    String(currentDateTime.getMonth() + 1).padStart(2, "0") +
                                    "-" +
                                    String(currentDateTime.getDate()).padStart(2, "0") +
                                    " " +
                                    String(currentDateTime.getHours()).padStart(2, "0") +
                                    ":" +
                                    String(currentDateTime.getMinutes()).padStart(2, "0") +
                                    ":" +
                                    String(currentDateTime.getSeconds()).padStart(2, "0");

                                try {
                                    new_quote_id = await self.env.services.orm.silent.create("pos.quote", [
                                        {
                                            quote_id: order_vals.quote_id,
                                            trackingNumber: order_vals.trackingNumber || "",
                                            session_id: order_vals.session_id,
                                            lines: order_vals.lines,
                                            note: order_vals.note || "",
                                            quote_sent: true,
                                            to_session_id: order_vals.to_session_id,
                                            state: "draft",
                                            partner_id: current_order.get_partner().id,
                                            user_id: order_vals.user_id,
                                            pricelist_id: order_vals.pricelist_id || false,
                                            table_json: order_vals.table_json || false,
                                            pos_res_info: order_vals.pos_res_info || false,
                                            amount_total: parseFloat(current_order.get_total_with_tax()),
                                            amount_tax: parseFloat(current_order.get_total_tax()),
                                            date_order: formattedDateOrder,
                                            seller_name: order_vals.seller_name,
                                        },
                                    ]);
                                    console.log("new_quote_id ===========", new_quote_id);
                                } catch (error) {
                                    console.log("Error in creating quote", error);
                                }

                                if (new_quote_id && current_order.get_partner()) {
                                    if (print_order_quote == true) self.pos.get_order().created_quote_id = new_quote_id;
                                    self.props.close();
                                    self.dialog.add(QuoteSendPopupWidget, {
                                        quote_status: "Pedido enviado a la caja destino",
                                        clear_order: true,
                                    });
                                }
                            } catch {
                                self.dialog.add(WkErrorNotifyPopopWidget, {
                                    title: "No se pudo guardar el pedido",
                                    body: "Verifica la conexión de red e inténtalo nuevamente.",
                                });
                            }
                        } else {
                            $("#order_quote_id_input_error").text("Este número de pedido ya fue utilizado.");
                            $("#order_quote_id_input_error").css("width", "75%");
                            $("#order_quote_id_input_error").css("padding-left", "18%");
                            $("#order_quote_id_input_error").show();
                        }
                    } catch {
                        self.dialog.add(WkErrorNotifyPopopWidget, {
                        title: "No se pudo guardar el pedido",
                        body: "Verifica la conexión de red e inténtalo nuevamente.",
                        });
                        $(".show_info").hide();
                    }
                }
            }
        }
    }
}

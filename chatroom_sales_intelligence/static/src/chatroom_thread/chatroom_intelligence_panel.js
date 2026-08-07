/** @odoo-module **/

import { Component } from "@odoo/owl";

/**
 * Panel lateral deslizable con la "inteligencia comercial" profunda de la
 * conversación: salud de la oportunidad, perfil de compra (Pareto) y
 * última venta. Recibe todo por props desde ChatroomThreadCore (parcheado
 * por chatroom_thread_core_patch.js) para no acoplarse a odoo.rpc por su
 * cuenta ni duplicar el estado del hilo.
 */
export class ChatroomIntelligencePanel extends Component {
    static template = "chatroom_sales_intelligence.ChatroomIntelligencePanel";
    static props = {
        open: Boolean,
        loading: Boolean,
        generating: { type: Boolean, optional: true },
        data: { type: [Object, { value: false }], optional: true },
        onClose: Function,
        onGenerateFollowup: Function,
    };

    formatMoney(amount) {
        if (amount === undefined || amount === null) {
            return "";
        }
        const formatted = Number(amount).toLocaleString(undefined, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
        const symbol = (this.props.data && this.props.data.currency_symbol) || "";
        if (this.props.data && this.props.data.currency_position === "after") {
            return `${formatted} ${symbol}`;
        }
        return `${symbol} ${formatted}`;
    }

    formatRelativeDays(days) {
        if (days === undefined || days === false || days === null) {
            return "Sin datos";
        }
        if (days === 0) {
            return "Hoy";
        }
        if (days === 1) {
            return "Hace 1 día";
        }
        return `Hace ${days} días`;
    }

    formatDate(value) {
        if (!value) {
            return "";
        }
        const isoLike = value.length > 10 ? value.replace(" ", "T") + "Z" : value + "T00:00:00Z";
        const dateObj = new Date(isoLike);
        return dateObj.toLocaleDateString();
    }

    rfmCategoryLabel() {
        return (this.props.data && this.props.data.rfm_category_label) || "Sin historial";
    }
}

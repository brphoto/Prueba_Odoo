/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ListController } from "@web/views/list/list_controller";
import { KanbanController } from "@web/views/kanban/kanban_controller";
import { ControlPanel } from "@web/search/control_panel/control_panel";

const MODEL_NAMES = {
    "account.move": "Factura",
    "chatroom.channel": "Conversación",
    "chatroom.scheduled.message": "Mensaje programado",
    "chatroom.template": "Plantilla de WhatsApp",
    "crm.lead": "Oportunidad",
    "product.product": "Producto",
    "project.task": "Tarea",
    "purchase.order": "Orden de compra",
    "res.partner": "Contacto",
    "sale.order": "Presupuesto",
};

function modelDisplayName(model) {
    return MODEL_NAMES[model] || model;
}

function isEmbeddedDialog(controller, options = {}) {
    // In Odoo 19 the reliable marker is the child environment created by
    // ActionDialog. `props.display` is not consistently present on every
    // list/kanban controller, so checking it alone silently falls back to the
    // standard action navigation.
    return (controller.env.inDialog || controller.props.display?.mode === "inDialog")
        && !options.newWindow;
}

function getEmbeddedReturnAction(controller) {
    const searchModel = controller.env.searchModel;
    const entries = controller.env.config.viewSwitcherEntries || [];
    const currentType = controller.props.type || "list";
    const viewTypes = [
        currentType,
        ...entries
            .filter((entry) => entry.multiRecord)
            .map((entry) => entry.type),
    ].filter((type, index, values) => values.indexOf(type) === index);
    const context = searchModel?.context || controller.props.context || {};
    const domain = searchModel?.domain || controller.props.domain || [];
    return {
        type: "ir.actions.act_window",
        name: controller.env.config.actionName || modelDisplayName(controller.props.resModel),
        res_model: controller.props.resModel,
        views: viewTypes.map((type) => [false, type]),
        view_mode: viewTypes.join(","),
        domain,
        context,
        target: "new",
    };
}

function restoreEmbeddedView(controller) {
    const action = getEmbeddedReturnAction(controller);
    if (!action.res_model) {
        return;
    }
    // The form close callback runs while Odoo is still removing the form
    // dialog. Queue the list action for the next task so it replaces the
    // closed dialog cleanly instead of being removed with it.
    setTimeout(() => controller.actionService.doAction(action), 0);
}

async function openEmbeddedForm(controller, record) {
    const model = record.resModel || controller.props.resModel;
    await controller.actionService.doAction(
        {
            type: "ir.actions.act_window",
            name: modelDisplayName(model),
            res_model: model,
            res_id: record.resId,
            views: [[false, "form"]],
            context: record.context || controller.props.context || {},
            view_mode: "form",
            target: "new",
        },
        {
            onClose: () => restoreEmbeddedView(controller),
        }
    );
}

async function createEmbeddedForm(controller) {
    const model = controller.props.resModel;
    await controller.actionService.doAction(
        {
            type: "ir.actions.act_window",
            name: modelDisplayName(model),
            res_model: model,
            views: [[false, "form"]],
            context: controller.props.context || {},
            view_mode: "form",
            target: "new",
        },
        {
            onClose: () => restoreEmbeddedView(controller),
        }
    );
}

patch(ListController.prototype, {
    setup() {
        super.setup(...arguments);
        // Keep a native Odoo affordance visible in embedded lists. It is
        // useful on touch devices and remains available if a user does not
        // know that a row is clickable.
        if (this.env.inDialog) {
            this.hasOpenFormViewButton = true;
        }
    },

    async createRecord() {
        if (this.env.inDialog) {
            await createEmbeddedForm(this);
            return;
        }
        return super.createRecord();
    },

    async openRecord(record, options = {}) {
        if (isEmbeddedDialog(this, options)) {
            const dirty = await record.isDirty();
            if (dirty) {
                await record.save();
            }
            await openEmbeddedForm(this, record);
            return;
        }
        return super.openRecord(record, options);
    },
});

patch(KanbanController.prototype, {
    async createRecord() {
        if (this.env.inDialog) {
            await createEmbeddedForm(this);
            return;
        }
        return super.createRecord();
    },

    async openRecord(record, options = {}) {
        if (isEmbeddedDialog(this, options)) {
            await openEmbeddedForm(this, record);
            return;
        }
        return super.openRecord(record, options);
    },
});

patch(ControlPanel.prototype, {
    async switchView(viewType, newWindow) {
        if (!this.env.inDialog) {
            return super.switchView(viewType, newWindow);
        }
        const searchModel = this.env.searchModel;
        const entries = this.env.config.viewSwitcherEntries || [];
        if (!searchModel || !entries.some((entry) => entry.type === viewType)) {
            return;
        }
        // actionService.switchView intentionally ignores requests while a
        // dialog is open. Recreate only the selected native view as a new
        // Odoo dialog, preserving the current domain and search context.
        const action = {
            type: "ir.actions.act_window",
            name: this.env.config.actionName,
            res_model: searchModel.resModel,
            views: [...new Set([
                viewType,
                ...entries.filter((entry) => entry.multiRecord).map((entry) => entry.type),
            ])].map((type) => [false, type]),
            domain: searchModel.domain,
            context: searchModel.context,
            target: "new",
        };
        this.dialogService.closeAll();
        await new Promise((resolve) => setTimeout(resolve, 0));
        return this.actionService.doAction(action);
    },
});

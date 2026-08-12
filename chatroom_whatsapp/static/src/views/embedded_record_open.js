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
    return controller.props.display?.mode === "inDialog"
        && !options.newWindow;
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
            target: "new",
        },
        {
            onClose: () => controller.model.root.load(),
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
            target: "new",
        },
        {
            onClose: () => controller.model.root.load(),
        }
    );
}

patch(ListController.prototype, {
    async createRecord() {
        if (this.props.display?.mode === "inDialog") {
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
        if (this.props.display?.mode === "inDialog") {
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

/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ListController } from "@web/views/list/list_controller";
import { KanbanController } from "@web/views/kanban/kanban_controller";

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
        && !options.newWindow
        && !controller.props.allowOpenAction;
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

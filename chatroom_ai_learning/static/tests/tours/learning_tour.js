/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * El panel del asistente muestra el nivel de autonomía del tipo de
 * conversación y, si hubo traspaso, el motivo. Luego se revisa la pantalla
 * de autonomía. Los datos los prepara `test_learning_tour.py`.
 */
registry.category("web_tour.tours").add("chatroom_ai_learning_tour", {
    url: "/odoo/action-chatroom_whatsapp.action_chatroom_app",
    steps: () => [
        {
            content: "Abrir la conversación traspasada",
            trigger: ".o_chatroom_app_list_item:contains('TOUR APRENDE')",
            run: "click",
            timeout: 60000,
        },
        {
            content: "El hilo está abierto",
            trigger: ".o_chatroom_header_name:contains('TOUR APRENDE')",
        },
        {
            content: "Mostrar el panel del contacto si está oculto",
            trigger: ".o_chatroom_app_panel_toggle",
            run: () => {
                if (!document.querySelector(".o_chatroom_ai_assistant")) {
                    document.querySelector(".o_chatroom_app_panel_toggle").click();
                }
            },
        },
        {
            content: "Abrir el Asistente IA",
            trigger: ".o_chatroom_ai_assistant .o_chatroom_contact_section_header",
            run: "click",
        },
        {
            content: "Se ve el nivel de autonomía de «Venta»",
            trigger: ".o_chatroom_ai_autonomy .badge:contains('Venta'):contains('Supervisado')",
        },
        {
            content: "Se ve por qué pasó a una persona",
            trigger: ".o_chatroom_ai_handoff:contains('Pide un humano')",
        },
    ],
});

registry.category("web_tour.tours").add("chatroom_ai_learning_levels_tour", {
    url: "/odoo/action-chatroom_ai_learning.action_ai_autonomy_level",
    steps: () => [
        {
            content: "La lista muestra los tipos de conversación y su situación",
            trigger: ".o_list_view .o_data_row:contains('Queja'):contains('Siempre')",
            timeout: 60000,
        },
        {
            content: "Abrir el nivel de «Venta»",
            trigger: ".o_list_view .o_data_row td[name='name']:contains('Venta')",
            run: "click",
        },
        {
            content: "El formulario explica qué falta para responder sola",
            trigger: ".o_form_view .alert-info:contains('Faltan')",
        },
    ],
});

/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * Panel compacto del Agente IA: se abre solo cuando hay algo por aprobar,
 * permite abrir la tarea, explica qué es y se puede ocultar. Los datos los
 * prepara `test_panel_tour.py`.
 */
registry.category("web_tour.tours").add("chatroom_ai_agent_panel_tour", {
    url: "/odoo/action-chatroom_whatsapp.action_chatroom_app",
    steps: () => [
        {
            content: "Abrir la conversación con una tarea por aprobar",
            trigger: ".o_chatroom_app_list_item:contains('TOUR AGENTE')",
            run: "click",
        },
        {
            content: "Abrir el panel lateral si está cerrado",
            trigger: ".o_chatroom_app_panel_toggle",
            run: () => {
                if (!document.querySelector(".o_chatroom_ai_agent")) {
                    document.querySelector(".o_chatroom_app_panel_toggle").click();
                }
            },
        },
        {
            content: "El encabezado avisa que hay algo por aprobar",
            trigger: ".o_chatroom_ai_agent .o_chatroom_ai_agent_badge:contains('Por aprobar')",
        },
        {
            content: "El panel se abrió solo y muestra la tarea primero",
            trigger: ".o_chatroom_ai_agent_body .o_chatroom_ai_agent_task.o_attention",
        },
        {
            content: "Un único selector de qué preparar, con su botón",
            trigger: ".o_chatroom_ai_agent_run select:has(option:contains('Plan completo de la conversación'))",
        },
        {
            content: "Revisar y aprobar abre la tarea",
            trigger: ".o_chatroom_ai_agent_task button:contains('Revisar y aprobar')",
            run: "click",
        },
        {
            content: "Se abre el formulario de la tarea en un diálogo",
            trigger: ".modal .o_form_view",
        },
        {
            content: "Cerrar el diálogo",
            trigger: ".modal .btn-close",
            run: "click",
        },
        {
            content: "Pedir la explicación del panel",
            trigger: ".o_chatroom_ai_agent_footer button:contains('¿Qué es esto?')",
            run: "click",
        },
        {
            content: "La ayuda explica la diferencia con el Asistente IA",
            trigger: ".o_chatroom_ai_agent_help:contains('no redacta mensajes')",
        },
        {
            content: "Ocultar el panel",
            trigger: ".o_chatroom_ai_agent_footer button:contains('Ocultar panel')",
            run: "click",
        },
        {
            content: "El panel del agente desaparece",
            trigger: ".o_chatroom_app:not(:has(.o_chatroom_ai_agent))",
        },
    ],
});

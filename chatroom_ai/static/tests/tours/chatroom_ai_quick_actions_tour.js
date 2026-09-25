/** @odoo-module **/

import { registry } from "@web/core/registry";

// Espera a que el compositor muestre el texto esperado: la respuesta del
// servidor llega unos milisegundos después del paso que la pidió.
async function waitForValue(selector, check, label) {
    const deadline = Date.now() + 8000;
    let value = "";
    while (Date.now() < deadline) {
        value = document.querySelector(selector)?.value || "";
        if (check(value)) {
            return;
        }
        await new Promise((resolve) => setTimeout(resolve, 100));
    }
    throw new Error(`${label}: "${value}"`);
}

/**
 * Recorrido de las acciones de IA en un navegador real: botón ✨ del
 * compositor, atajos "/" con filtro y teclado, reescritura del borrador y
 * panel "Asistente IA" con acciones configurables. Los datos (y la IA
 * simulada) los prepara `test_quick_actions_tour.py`.
 */
registry.category("web_tour.tours").add("chatroom_ai_quick_actions_tour", {
    url: "/odoo/action-chatroom_whatsapp.action_chatroom_app",
    steps: () => [
        {
            content: "Abrir la conversación de prueba",
            trigger: ".o_chatroom_app_list_item:contains('TOUR IA')",
            run: "click",
        },
        {
            content: "El hilo de la conversación está abierto",
            trigger: ".o_chatroom_header_name:contains('TOUR IA')",
        },
        {
            content: "El compositor tiene el botón de acciones de IA",
            trigger: ".o_chatroom_ai_quick_btn",
            run: "click",
        },
        {
            content: "El menú lista las acciones configuradas, con su atajo",
            trigger: ".o_chatroom_ai_quick_menu .o_chatroom_ai_quick_item:contains('Mejorar mi borrador'):contains('/mejorar')",
        },
        {
            content: "Cerrar el menú con el mismo botón",
            trigger: ".o_chatroom_ai_quick_btn",
            run: "click",
        },
        {
            content: "El menú se cerró",
            trigger: ".o_chatroom_composer:not(:has(.o_chatroom_ai_quick_menu))",
        },
        {
            content: "Escribir un borrador y el atajo /mej",
            trigger: ".o_chatroom_composer_textarea",
            run: "edit hola que tal le cuento /mej",
        },
        {
            content: "El atajo filtra el menú: solo aparece «Mejorar mi borrador»",
            trigger: ".o_chatroom_ai_quick_menu:has(.o_chatroom_ai_quick_item:contains('Mejorar mi borrador')):not(:has(.o_chatroom_ai_quick_item:contains('Resumen de conversación')))",
        },
        {
            content: "Enter ejecuta la acción resaltada",
            trigger: ".o_chatroom_composer_textarea",
            run: "press Enter",
        },
        {
            content: "El borrador se reemplazó por la versión mejorada (y no se envió)",
            trigger: ".o_chatroom_composer_textarea",
            run: () => waitForValue(
                ".o_chatroom_composer_textarea",
                (value) => value === "Hola, ¿qué tal? Le cuento.",
                "El borrador no se reescribió"),
        },
        {
            content: "El menú de atajos se cerró tras usarlo",
            trigger: ".o_chatroom_composer:not(:has(.o_chatroom_ai_quick_menu))",
        },
        {
            content: "Abrir el panel lateral de la conversación si está cerrado",
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
            content: "El selector ofrece las acciones configurables",
            trigger: ".o_chatroom_ai_assistant_compact_bar select:has(option:contains('Responder con precio y stock'))",
        },
        {
            content: "Se muestra para qué sirve la acción elegida",
            trigger: ".o_chatroom_ai_action_hint:contains('Redacta la respuesta')",
        },
        {
            content: "Ejecutar «Respuesta sugerida»",
            trigger: ".o_chatroom_ai_assistant_compact_bar .btn-primary:enabled",
            run: "click",
        },
        {
            content: "Aparece el borrador de IA para revisar, con la acción que lo generó",
            trigger: ".o_chatroom_ai_assistant_result:contains('Respuesta sugerida')",
        },
        {
            content: "El borrador tiene el texto simulado",
            trigger: ".o_chatroom_ai_assistant_result textarea",
            run: () => waitForValue(
                ".o_chatroom_ai_assistant_result textarea",
                (value) => value.includes("Hola, ¿qué tal? Le cuento."),
                "Borrador inesperado"),
        },
        {
            content: "Los detalles de seguridad están plegados para ahorrar espacio",
            trigger: ".o_chatroom_ai_details_toggle:contains('Detalles de seguridad')",
            run: "click",
        },
        {
            content: "Al desplegarlos aparecen guardia y aprobación humana",
            trigger: ".o_chatroom_ai_assistant_meta:contains('Aprobación humana')",
        },
    ],
});

/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * Recorrido de humo de la app de Chatroom en un navegador real.
 *
 * Cubre lo que no puede cubrir un test de Python: que el bundle compile,
 * que la app monte y que las tres piezas de interfaz que mas logica
 * tienen se comporten como se espera.
 *
 * Los datos los prepara `test_chatroom_tour.py`: dos conversaciones, una
 * con historial largo (para la paginacion) y otra corta.
 */
registry.category("web_tour.tours").add("chatroom_app_smoke_tour", {
    url: "/odoo/action-chatroom_whatsapp.action_chatroom_app",
    steps: () => [
        {
            content: "La bandeja carga y muestra las conversaciones",
            trigger: ".o_chatroom_app_list .o_chatroom_app_list_item",
            run: () => {},
        },
        {
            content: "Abrir la conversacion con historial largo",
            trigger: ".o_chatroom_app_list_item:contains('TOUR LARGA')",
            run: "click",
        },
        {
            content: "El hilo carga solo la ultima tanda de mensajes",
            trigger: ".o_chatroom_thread_messages .o_chatroom_load_older button",
            run: () => {},
        },
        {
            content: "El mensaje mas nuevo esta a la vista (se cargo el final, no el principio)",
            trigger: ".o_chatroom_thread_messages:contains('mensaje-tour-79')",
            run: () => {},
        },
        {
            content: "Los mensajes viejos todavia NO estan cargados",
            trigger: ".o_chatroom_thread_messages:not(:contains('mensaje-tour-00'))",
            run: () => {},
        },
        {
            content: "Pedir los mensajes anteriores",
            trigger: ".o_chatroom_load_older button",
            run: "click",
        },
        {
            content: "Ahora si aparecen los mas viejos",
            trigger: ".o_chatroom_thread_messages:contains('mensaje-tour-00')",
            run: () => {},
        },
        {
            content: "Escribir un borrador en esta conversacion",
            trigger: ".o_chatroom_composer_textarea",
            run: "edit BORRADOR-DE-PRUEBA",
        },
        {
            content: "Cambiar a la otra conversacion",
            trigger: ".o_chatroom_app_list_item:contains('TOUR CORTA')",
            run: "click",
        },
        {
            content: "El hilo abierto es realmente el de la otra conversacion",
            trigger: ".o_chatroom_header_name:contains('TOUR CORTA')",
            run: () => {},
        },
        {
            content: "El compositor de la otra conversacion arranca vacio",
            trigger: ".o_chatroom_composer_textarea",
            run: () => {
                const value = document.querySelector(
                    ".o_chatroom_composer_textarea").value;
                if (value !== "") {
                    throw new Error(
                        `El borrador se filtro a otra conversacion: "${value}"`);
                }
            },
        },
        {
            content: "Volver a la primera conversacion",
            trigger: ".o_chatroom_app_list_item:contains('TOUR LARGA')",
            run: "click",
        },
        {
            content: "El hilo abierto vuelve a ser el de la primera conversacion",
            trigger: ".o_chatroom_header_name:contains('TOUR LARGA')",
            run: () => {},
        },
        {
            // Como trigger (no como assert dentro de `run`) para que el
            // tour ESPERE a que termine la carga asincrona del hilo antes
            // de mirar el compositor.
            content: "El borrador sobrevivio al cambio de conversacion",
            trigger: ".o_chatroom_composer_textarea:value('BORRADOR-DE-PRUEBA')",
            run: () => {},
        },
        {
            content: "Abrir la busqueda de mensajes",
            trigger: ".o_chatroom_message_tools button[title='Buscar en la conversación']",
            run: "click",
        },
        {
            content: "Buscar un mensaje que quedo FUERA de la tanda cargada",
            trigger: ".o_chatroom_message_search input",
            run: "edit mensaje-tour-03",
        },
        {
            content: "La busqueda del servidor lo encuentra igual",
            trigger: ".o_chatroom_thread_messages:contains('mensaje-tour-03')",
            run: () => {},
        },
    ],
});

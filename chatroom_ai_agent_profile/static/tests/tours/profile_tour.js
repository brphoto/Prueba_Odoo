/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * Perfil del agente: preparación, probador con respuesta simulada y el
 * guion en el panel del chat. Los datos (y la IA simulada) los prepara
 * `test_profile_tour.py`.
 */
registry.category("web_tour.tours").add("chatroom_ai_agent_profile_tour", {
    url: "/odoo/action-chatroom_ai_agent_profile.action_agent_profile",
    steps: () => [
        {
            content: "Abrir el perfil principal",
            trigger: ".o_list_view .o_data_row td[name='name']:contains('Agente principal')",
            run: "click",
            timeout: 60000,
        },
        {
            content: "El perfil muestra qué falta para atender solo",
            trigger: ".o_agent_profile_readiness:contains('Conocimiento publicado')",
        },
        {
            content: "Abrir el probador",
            trigger: "button[name='action_open_simulator']",
            run: "click",
        },
        {
            content: "Escribir como cliente",
            trigger: ".modal .o_agent_sim_input textarea",
            run: "edit ¿Cuál es el horario de atención?",
        },
        {
            content: "Enviar",
            trigger: ".modal button[name='action_send']",
            run: "click",
        },
        {
            content: "La IA responde con el conocimiento",
            trigger: ".modal .o_agent_sim_ai:contains('lunes a viernes')",
        },
        {
            content: "Y explica qué haría en producción",
            trigger: ".modal .o_agent_sim_ai .badge:contains('Se enviaría sola')",
        },
        {
            content: "Cerrar el probador",
            trigger: ".modal .modal-footer button.btn-secondary:contains('Cerrar')",
            run: "click",
        },
        {
            content: "El probador se cerró",
            trigger: "body:not(:has(.modal .o_agent_sim_chat))",
        },
    ],
});

registry.category("web_tour.tours").add("chatroom_ai_agent_playbook_tour", {
    url: "/odoo/action-chatroom_whatsapp.action_chatroom_app",
    steps: () => [
        {
            content: "Abrir la conversación con un guion en curso",
            trigger: ".o_chatroom_app_list_item:contains('TOUR GUION')",
            run: "click",
            timeout: 60000,
        },
        {
            content: "El hilo está abierto",
            trigger: ".o_chatroom_header_name:contains('TOUR GUION')",
            timeout: 20000,
        },
        {
            content: "Abrir el panel lateral si está cerrado",
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
            content: "Se ve el avance del guion",
            trigger: ".o_chatroom_ai_playbook .badge:contains('Cotización o compra'):contains('2/3')",
        },
        {
            content: "La lista muestra que la conversación está con una persona",
            trigger: ".o_chatroom_app_list_item:contains('TOUR GUION') .o_ai_list_state.o_ai_state_human",
        },
        {
            content: "El aviso de traspaso muestra los datos reunidos",
            trigger: ".o_chatroom_ai_handoff .o_ai_handoff_data:contains('sillas')",
        },
        {
            content: "Tomar la conversación",
            trigger: ".o_chatroom_ai_handoff button.o_ai_take_over",
            run: "click",
        },
        {
            content: "Ya está a mi cargo: el botón desaparece",
            trigger: ".o_chatroom_ai_handoff:not(:has(button.o_ai_take_over))",
        },
    ],
});

registry.category("web_tour.tours").add("chatroom_ai_inbox_tour", {
    url: "/odoo/action-chatroom_ai_agent_profile.action_ai_inbox",
    steps: () => [
        {
            content: "La bandeja muestra el borrador con lo que escribió el cliente",
            trigger: ".o_ai_inbox .o_data_row:contains('TOUR BANDEJA'):contains('¿Tienen sillas')",
            timeout: 60000,
        },
        {
            content: "Aprobar y enviar",
            trigger: ".o_ai_inbox .o_data_row:contains('TOUR BANDEJA') button[name='action_approve_and_send']",
            run: "click",
        },
        {
            content: "Se envió y sale de la bandeja",
            trigger: ".o_view_nocontent, .o_ai_inbox:not(:has(.o_data_row:contains('TOUR BANDEJA')))",
        },
    ],
});

/**
 * Centro de IA: aprobar un borrador corregido, cambiar la autonomía,
 * publicar información en un paso y preguntarle a los datos.
 */
registry.category("web_tour.tours").add("chatroom_ai_center_tour", {
    url: "/odoo/action-chatroom_ai_agent_profile.action_ai_center",
    steps: () => [
        {
            content: "Hoy: el borrador con la pregunta del cliente",
            trigger: ".o_ai_center .o_ai_draft_card:contains('TOUR CENTRO'):contains('¿Arman los muebles?')",
            timeout: 60000,
        },
        {
            content: "Corregir la respuesta",
            trigger: ".o_ai_draft_card:contains('TOUR CENTRO') textarea.o_ai_draft_text",
            run: "edit Sí, el armado es gratis en la ciudad.",
        },
        {
            content: "Enviar",
            trigger: ".o_ai_draft_card:contains('TOUR CENTRO') .o_ai_draft_send",
            run: "click",
        },
        {
            content: "Ya no quedan pendientes",
            trigger: ".o_ai_center .o_ai_center_empty",
        },
        {
            content: "Ir a Configurar",
            trigger: ".o_ai_center_tab[data-tab='setup']",
            run: "click",
        },
        {
            content: "Elegir el modo Prudente",
            trigger: ".o_ai_mode[data-mode='prudent']",
            run: "click",
        },
        {
            content: "El modo queda activo",
            trigger: ".o_ai_mode.active[data-mode='prudent']",
        },
        {
            content: "Escribir información nueva",
            trigger: "textarea.o_ai_knowledge_text",
            run: "edit Armamos los muebles gratis dentro de la ciudad.",
        },
        {
            content: "Publicar en un paso",
            trigger: ".o_ai_knowledge_publish",
            run: "click",
        },
        {
            content: "Queda publicado al instante",
            trigger: ".o_notification:contains('la IA ya lo usa')",
        },
        {
            content: "Ir a Resultados",
            trigger: ".o_ai_center_tab[data-tab='results']",
            run: "click",
        },
        {
            content: "Preguntarle a los datos",
            trigger: ".o_ai_ask .btn-light:contains('¿Qué preguntan más')",
            run: "click",
        },
        {
            content: "La respuesta aparece",
            trigger: ".o_ai_ask_answer:contains('armado')",
        },
    ],
});

/** El borrador de la IA aparece escrito en el cuadro del chat. */
registry.category("web_tour.tours").add("chatroom_ai_composer_draft_tour", {
    url: "/odoo/action-chatroom_whatsapp.action_chatroom_app",
    steps: () => [
        {
            content: "Abrir la conversación con un borrador",
            trigger: ".o_chatroom_app_list_item:contains('TOUR BORRADOR')",
            run: "click",
            timeout: 60000,
        },
        {
            content: "El aviso del borrador de la IA",
            trigger: ".o_ai_composer_draft:contains('La IA dejó escrita')",
            timeout: 20000,
        },
        {
            content: "El texto ya está en el cuadro",
            trigger: "textarea.o_chatroom_composer_textarea",
            run() {
                const value = document.querySelector("textarea.o_chatroom_composer_textarea").value;
                if (!value.includes("Sí, hacemos envíos a Cuenca")) {
                    throw new Error("El cuadro no tiene el borrador: " + value);
                }
            },
        },
        {
            content: "Editarlo muestra que aprenderá la corrección",
            trigger: "textarea.o_chatroom_composer_textarea",
            run: "edit Sí, enviamos a Cuenca en 48 horas.",
        },
        {
            content: "Aviso de corrección",
            trigger: ".o_ai_composer_draft:contains('aprende tu versión')",
        },
        {
            content: "Descartar el borrador",
            trigger: ".o_ai_composer_draft_discard",
            run: "click",
        },
        {
            content: "El aviso desaparece",
            trigger: ".o_chatroom_composer_input:not(:has(.o_ai_composer_draft))",
        },
    ],
});

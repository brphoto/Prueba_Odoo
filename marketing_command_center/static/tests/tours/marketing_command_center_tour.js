/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * Recorrido de humo del centro de mando de marketing.
 *
 * Comprueba lo que ningún test de ORM puede comprobar: que la vista
 * compile, que el formulario monte con datos y que la navegación del panel
 * funcione en pantalla. Fue este tour el que destapó que el administrador
 * no pertenecía a ningún grupo de marketing y recibía un AccessError al
 * abrir el menú: los tests de Python corren como superusuario y por eso no
 * lo veían.
 *
 * QUÉ NO CUBRE: el recálculo automático al cambiar el período o la red.
 * En este entorno no se consiguió que un tour confirmara la edición de un
 * campo (ni el `o_select_menu` de un Selection ni el input de un Integer
 * llegan a marcar el registro como modificado), así que el guardado nunca
 * se dispara y la comprobación no tendría valor. Ese comportamiento está
 * cubierto por los tests de Python
 * (`test_dashboard_recalculates_when_the_period_changes` y el del filtro
 * de red), que ejercitan el mismo `write` que usa el cliente web.
 *
 * Los datos demo los siembra el test de Python antes de arrancar, y los
 * selectores se anclan en nombres de campo y no en la clase del `<form>`,
 * que Odoo no traslada al DOM.
 */
registry.category("web_tour.tours").add("marketing_command_center_tour", {
    url: "/odoo/action-marketing_command_center.action_marketing_social_dashboard",
    steps: () => [
        {
            content: "El centro de mando abre en su formulario",
            trigger: ".o_form_view [name='platform_filter']",
            run: () => {},
        },
        {
            content: "El panel llega con datos y no en blanco",
            trigger: ".o_form_view [name='publication_count']",
            run: () => {
                const value = Number(document.querySelector(
                    "[name='publication_count']").textContent.replace(/[^0-9]/g, "") || 0);
                if (!value) {
                    throw new Error("El panel abrió sin publicaciones contadas.");
                }
            },
        },
        {
            content: "Los indicadores de alcance también llegaron calculados",
            trigger: ".o_form_view [name='reach_total']",
            run: () => {
                const value = Number(document.querySelector(
                    "[name='reach_total']").textContent.replace(/[^0-9]/g, "") || 0);
                if (!value) {
                    throw new Error("El panel abrió sin alcance calculado.");
                }
            },
        },
        {
            content: "Abrir la evolución del período",
            trigger: "button[name='action_open_trend']",
            run: "click",
        },
        {
            content: "Se abre la serie de métricas en gráfico",
            trigger: ".o_graph_view, .o_graph_renderer, .o_graph_canvas_container",
            // La vista de grafico carga su propio bundle. En una corrida
            // donde se acaban de actualizar muchos modulos, Odoo lo
            // regenera en ese momento y los 10 s por defecto se quedan
            // cortos: el paso fallaba de forma intermitente sin que
            // hubiera nada roto.
            timeout: 30000,
            run: () => {},
        },
        {
            content: "Volver al centro de mando",
            trigger: ".breadcrumb-item:not(.active) a, .o_breadcrumb a",
            run: "click",
        },
        {
            content: "El panel vuelve a estar en pantalla",
            trigger: ".o_form_view [name='platform_filter']",
            run: () => {},
        },
        {
            content: "Abrir la pestaña de comparación y alertas",
            trigger: ".o_notebook .nav-link:contains('Comparación')",
            run: "click",
        },
        {
            content: "La variación frente al período anterior está a la vista",
            trigger: "[name='reach_delta_pct']",
            run: () => {},
        },
        {
            content: "Abrir la pestaña del embudo CRM",
            trigger: ".o_notebook .nav-link:contains('Embudo CRM')",
            run: "click",
        },
        {
            content: "El embudo muestra la atribución social",
            trigger: "[name='crm_lead_count']",
            run: () => {},
        },
    ],
});

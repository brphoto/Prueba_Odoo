/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * Pantalla del comparativo en un navegador real: cuadro comparativo,
 * análisis, revisión de una cotización y aprobación. Los datos (con la IA
 * simulada) los prepara `test_compare_tour.py`.
 */
registry.category("web_tour.tours").add("insurance_compare_tour", {
    url: "/odoo/action-insurance_ai_compare.action_insurance_compare",
    steps: () => [
        {
            content: "Abrir el comparativo analizado",
            // En la referencia: la columna del asesor abre la ficha del usuario.
            trigger: ".o_data_row:contains('Cliente Tour Seguros') td[name='name']",
            run: "click",
        },
        {
            content: "El estado es Analizado",
            trigger: ".o_statusbar_status .o_arrow_button_current:contains('Analizado')",
        },
        {
            content: "Ir al cuadro comparativo",
            trigger: ".o_notebook .nav-link:contains('Cuadro comparativo')",
            run: "click",
        },
        {
            content: "El cuadro muestra las aseguradoras, las coberturas y la descartada",
            trigger: ".o_insurance_matrix:contains('Aseguradora Norte QA'):contains('Responsabilidad civil'):contains('Descartada')",
        },
        {
            content: "La opción recomendada está resaltada",
            trigger: ".o_insurance_matrix th.o_insurance_best:contains('Aseguradora Norte QA')",
        },
        {
            content: "Ir al análisis",
            trigger: ".o_notebook .nav-link:contains('Análisis y recomendación')",
            run: "click",
        },
        {
            content: "Se ven ventajas y desventajas por aseguradora",
            trigger: ".o_insurance_offer_card:contains('Auto de reemplazo')",
        },
        {
            content: "Volver a las cotizaciones",
            trigger: ".o_notebook .nav-link:contains('Cotizaciones')",
            run: "click",
        },
        {
            content: "Abrir la revisión de la primera cotización",
            trigger: ".o_field_one2many[name='offer_ids'] .o_data_row:first button[name='action_open']",
            run: "click",
        },
        {
            content: "El diálogo muestra las coberturas leídas, con lo dudoso resaltado",
            trigger: ".modal .o_field_one2many[name='line_ids'] .o_data_row",
        },
        {
            content: "Cerrar la revisión",
            trigger: ".modal .btn-close",
            run: "click",
        },
        {
            content: "Aprobar el comparativo",
            trigger: ".o_form_statusbar button[name='action_approve']",
            run: "click",
        },
        {
            content: "Queda aprobado y aparece el envío por WhatsApp",
            trigger: ".o_form_statusbar button[name='action_send_whatsapp']",
        },
        {
            content: "El estado cambió a Aprobado",
            trigger: ".o_statusbar_status .o_arrow_button_current:contains('Aprobado')",
        },
    ],
});

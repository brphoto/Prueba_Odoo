# -*- coding: utf-8 -*-
{
    'name': "Inteligencia de Clientes (RFM / Pareto)",

    'summary': """
        Clasificación RFM/ABC, alerta de oportunidades estancadas,
        histórico de ventas y análisis Pareto (80/20) de productos por
        contacto. Módulo independiente: no depende de ningún canal de
        comunicación (WhatsApp, email, etc.), solo de CRM/Ventas/
        Facturación.""",

    'description': """
Inteligencia de Clientes (RFM / Pareto)
==========================================

Agrega a **Contactos** y **CRM** la capa de análisis comercial que
cualquier equipo (ventas, marketing, atención al cliente) puede
necesitar, sin importar por qué canal habla con el cliente:

* **Clasificación RFM/ABC**: cron diario que calcula, para toda la
  cartera con al menos una factura, un score 1-100 (percentiles de
  Recencia + Frecuencia + Monto, pesos configurables desde Ajustes —
  20%/30%/50% por defecto) y lo traduce a categoría A/B/C. Al vivir en
  ``res.partner``, sirve tal cual para segmentar campañas de Email/SMS
  Marketing por ``rfm_category``/``rfm_score``.
* **Oportunidades estancadas**: sobre ``crm.lead``, un semáforo
  verde/amarillo/rojo según los días desde la última gestión real
  (cambio de etapa, nota/comentario humano o actividad).
* **Métricas históricas de venta**: total facturado, cantidad de
  facturas, fecha de la última venta y ticket promedio del contacto.
* **Análisis Pareto (80/20)**: producto más comprado y detalle de los
  top 5 productos, con un botón inteligente en la ficha de contacto.

Por qué es un módulo aparte
------------------------------
Este módulo nació dentro de ``chatroom_sales_intelligence`` (para
mostrar esta misma información en el chat de WhatsApp), pero la
clasificación de clientes es útil para cualquier equipo, no solo para
quien atiende WhatsApp. Se separó para que se pueda instalar sin
ninguna dependencia de mensajería: solo requiere ``crm``, ``sale`` y
``account``, los módulos nativos de Odoo (más ``kpi_engine``, el mixin
técnico de "objetivo de KPI" que también usa ``chatroom_whatsapp`` sin
que ninguno de los dos dependa del otro). ``chatroom_sales_intelligence``
ahora depende de este módulo (no al revés) para no duplicar la lógica.
    """,

    'author': "Bryan Cando",
    'website': "https://github.com/brphoto/Prueba_Odoo",
    'license': 'LGPL-3',
    'icon': '/crm_customer_intelligence/static/description/icon.svg',

    'category': 'Sales/CRM',
    'version': '19.0.1.1.3',

    'depends': ['crm', 'sale', 'account', 'kpi_engine'],

    'data': [
        'security/crm_intelligence_security.xml',
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'data/kpi_definition_data.xml',
        'data/rfm_segment_data.xml',
        'data/rfm_category_data.xml',
        'data/rfm_reactivation_rule_data.xml',
        'views/crm_intelligence_menus.xml',
        'views/kpi_definition_views.xml',
        'views/rfm_dashboard_report_views.xml',
        'views/crm_kpi_snapshot_views.xml',
        'views/crm_kpi_target_views.xml',
        'views/rfm_segment_views.xml',
        'views/rfm_segment_automation_views.xml',
        'views/rfm_category_views.xml',
        'views/management_alert_views.xml',
        'views/res_partner_views.xml',
        'views/res_config_settings_views.xml',
        'views/rfm_reactivation_rule_views.xml',
    ],

    'assets': {
        'web.assets_backend': [
            'crm_customer_intelligence/static/src/rfm_dashboard/rfm_dashboard.js',
            'crm_customer_intelligence/static/src/rfm_dashboard/rfm_dashboard.xml',
            'crm_customer_intelligence/static/src/rfm_dashboard/rfm_dashboard.scss',
        ],
        'web.assets_web_dark': [
            'crm_customer_intelligence/static/src/rfm_dashboard/rfm_dashboard.dark.scss',
        ],
    },

    'demo': [],

    'installable': True,
    'application': False,
    'auto_install': False,
}

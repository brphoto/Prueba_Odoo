# -*- coding: utf-8 -*-
{
    'name': "Chatroom - Inteligencia Comercial",

    'summary': """
        Agrega inteligencia comercial (RFM, oportunidades estancadas,
        histórico de ventas, Pareto de productos) al Chatroom WhatsApp,
        sin modificarlo: es un módulo 100% opcional y desacoplado.""",

    'description': """
Chatroom - Inteligencia Comercial
===================================

Extiende (sin tocar) el módulo **Chatroom WhatsApp & Redes Sociales** con
un panel de inteligencia comercial pensado para que un vendedor prepare
una conversación sin salir del chat:

* **Oportunidades estancadas**: alerta en semáforo (verde/amarillo/rojo)
  según los días sin gestión de la oportunidad vinculada a la conversación.
* **Clasificación RFM/ABC**: categoría (A/B/C) y score (1-100) calculados
  por un cron diario a partir de Recencia, Frecuencia y Monto de compra.
* **Métricas históricas de venta**: total facturado, cantidad de
  facturas, fecha de la última venta y ticket promedio del contacto.
* **Análisis Pareto (80/20)**: producto más comprado y detalle de los
  top 5 productos del contacto.
* **Micro-indicadores en el chat**: badge de categoría junto al nombre
  del contacto, punto de alerta si la oportunidad está estancada, y un
  aviso contextual con botón rápido para escribir un mensaje de
  seguimiento.
* **Panel lateral deslizable** ("swipe" desde el chat, o botón visible
  para mouse/teclado) con la ficha comercial completa: salud de la
  oportunidad, perfil de compra en chips visuales, última venta, y un
  botón para generar con IA una excusa de seguimiento.
* **"Mis pendientes de hoy"**: pantalla nueva que junta, para el
  usuario logueado, sus conversaciones sin gestión reciente y sus
  oportunidades estancadas, para arrancar el día sabiendo a quién
  contactar primero sin recorrer el kanban ni el pipeline.
* **Campañas de WhatsApp por categoría RFM**: mandar una plantilla
  aprobada a todos los contactos de una o más categorías (A/B/C) de un
  solo clic, respetando la baja de WhatsApp de cada contacto.
* **Ficha de Oportunidad (CRM)**: botón inteligente "WhatsApp" con la
  cantidad de conversaciones del contacto, categoría/score RFM e
  histórico de compras a la vista, y un banner con el último mensaje
  de WhatsApp con acceso directo para abrir la conversación real y
  responder sin salir del CRM.

Diseño modular
----------------
Este módulo **depende de** ``chatroom_whatsapp`` y de
``crm_customer_intelligence`` (que a su vez solo depende de ``crm``,
``sale`` y ``account`` — sin ningún canal de mensajería), pero ninguno
de los dos depende de este ni sabe que existe: toda la integración se
hace por herencia de vistas (``ir.ui.view`` para el kanban) y por
extensión de los componentes OWL existentes (``t-inherit`` de templates
+ ``patch()`` de las clases JS). Desinstalar este módulo deja tanto el
chatroom como la clasificación de clientes exactamente como estaban
antes de instalarlo.

La clasificación RFM/ABC, el semáforo de oportunidades estancadas y el
análisis Pareto viven en ``crm_customer_intelligence`` (instalable solo
si se necesita esa inteligencia comercial sin el chatroom, por ejemplo
para segmentar campañas de Email/SMS Marketing); este módulo solo
agrega la capa visual que los muestra dentro del chat.
    """,

    'author': "Bryan Cando",
    'website': "https://github.com/brphoto/Prueba_Odoo",
    'license': 'LGPL-3',
    'icon': '/chatroom_sales_intelligence/static/description/icon.svg',

    'category': 'Sales/CRM',
    'version': '19.0.1.0.15',

    'depends': ['chatroom_whatsapp', 'crm_customer_intelligence', 'crm_stagnation_intelligence'],

    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        # chatroom_menus.xml define menu_chatroom_commercial: tiene que
        # cargar antes que cualquier vista que lo use como parent.
        'views/chatroom_menus.xml',
        'views/chatroom_channel_views.xml',
        'views/crm_lead_views.xml',
        'views/chatroom_campaign_views.xml',
        'views/crm_segment_whatsapp_views.xml',
        'views/management_report_subscription_views.xml',
        'views/chat_automation_rule_views.xml',
        'views/res_config_settings_views.xml',
        'views/ai_knowledge_base_views.xml',
    ],

    'assets': {
        'web.assets_backend': [
            'chatroom_sales_intelligence/static/src/chatroom_thread/chatroom_intelligence_panel.js',
            'chatroom_sales_intelligence/static/src/chatroom_thread/chatroom_intelligence_panel.xml',
            'chatroom_sales_intelligence/static/src/chatroom_app/chatroom_active_opportunities.xml',
            'chatroom_sales_intelligence/static/src/chatroom_thread/chatroom_thread_core_patch.js',
            'chatroom_sales_intelligence/static/src/chatroom_thread/chatroom_thread_core_patch.xml',
            'chatroom_sales_intelligence/static/src/chatroom_thread/chatroom_intelligence.scss',
            'chatroom_sales_intelligence/static/src/chatroom_app/chatroom_app_patch.js',
            'chatroom_sales_intelligence/static/src/chatroom_app/chatroom_app_patch.xml',
            'chatroom_sales_intelligence/static/src/chatroom_app/chatroom_systray_patch.js',
            'chatroom_sales_intelligence/static/src/my_followups/my_followups_dashboard.js',
            'chatroom_sales_intelligence/static/src/my_followups/my_followups_dashboard.xml',
            'chatroom_sales_intelligence/static/src/my_followups/my_followups_dashboard.scss',
            'chatroom_sales_intelligence/static/src/executive_dashboard/executive_dashboard.js',
            'chatroom_sales_intelligence/static/src/executive_dashboard/executive_dashboard.xml',
            'chatroom_sales_intelligence/static/src/executive_dashboard/executive_dashboard.scss',
        ],
        'web.assets_web_dark': [
            'chatroom_sales_intelligence/static/src/chatroom_thread/chatroom_intelligence.dark.scss',
            'chatroom_sales_intelligence/static/src/my_followups/my_followups_dashboard.dark.scss',
            'chatroom_sales_intelligence/static/src/executive_dashboard/executive_dashboard.dark.scss',
        ],
    },

    'demo': [],

    'installable': True,
    'application': False,
    'auto_install': False,
}

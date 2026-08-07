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

Diseño modular
----------------
Este módulo **depende de** ``chatroom_whatsapp`` (además de ``crm``,
``sale`` y ``account``), pero ``chatroom_whatsapp`` no depende de él ni
sabe que existe: toda la integración se hace por herencia de vistas
(``ir.ui.view`` para el formulario de contacto y el kanban) y por
extensión de los componentes OWL existentes (``t-inherit`` de templates +
``patch()`` de las clases JS). Desinstalar este módulo deja el chatroom
exactamente como estaba antes de instalarlo.
    """,

    'author': "Bryan Cando",
    'website': "https://github.com/brphoto/Prueba_Odoo",
    'license': 'LGPL-3',

    'category': 'Sales/CRM',
    'version': '19.0.1.0.0',

    'depends': ['chatroom_whatsapp', 'crm', 'sale', 'account'],

    'data': [
        'data/ir_cron_data.xml',
        'views/res_partner_views.xml',
        'views/chatroom_channel_views.xml',
    ],

    'assets': {
        'web.assets_backend': [
            'chatroom_sales_intelligence/static/src/chatroom_thread/chatroom_intelligence_panel.js',
            'chatroom_sales_intelligence/static/src/chatroom_thread/chatroom_intelligence_panel.xml',
            'chatroom_sales_intelligence/static/src/chatroom_thread/chatroom_thread_core_patch.js',
            'chatroom_sales_intelligence/static/src/chatroom_thread/chatroom_thread_core_patch.xml',
            'chatroom_sales_intelligence/static/src/chatroom_thread/chatroom_intelligence.scss',
            'chatroom_sales_intelligence/static/src/chatroom_app/chatroom_app_patch.js',
            'chatroom_sales_intelligence/static/src/chatroom_app/chatroom_app_patch.xml',
        ],
        'web.assets_web_dark': [
            'chatroom_sales_intelligence/static/src/chatroom_thread/chatroom_intelligence.dark.scss',
        ],
    },

    'demo': [],

    'installable': True,
    'application': False,
    'auto_install': False,
}

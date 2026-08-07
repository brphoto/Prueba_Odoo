# -*- coding: utf-8 -*-
{
    'name': "Chatroom WhatsApp & Redes Sociales",

    'summary': """
        Chatroom omnicanal integrado con la API oficial de WhatsApp Business
        (Meta Cloud API) y Messenger/Instagram, sin depender de proveedores
        externos (Twilio, Chat-API, Wassenger, etc.).""",

    'description': """
Chatroom WhatsApp & Redes Sociales
===================================

Conecta Odoo directamente con la **API oficial de Meta (WhatsApp Business
Cloud API)**, sin pasar por conectores externos ni por el WhatsApp Web
"por QR" (no soportado por Meta y contrario a los Términos de Servicio de
WhatsApp para uso comercial).

Funcionalidades principales
----------------------------
* Bandeja de conversaciones tipo "chatroom" para WhatsApp, Messenger e
  Instagram Direct (todos corren sobre el mismo Graph API de Meta).
* Webhook propio (``/chatroom_whatsapp/webhook``) para recibir mensajes y
  actualizaciones de estado en tiempo real, sin middleware de terceros.
* Creación automática de contactos (``res.partner``) a partir del número
  de WhatsApp cuando llega un mensaje nuevo.
* Flujo comercial: crear Oportunidad (CRM) o Presupuesto (Ventas)
  directamente desde una conversación.
* Sugerencia de respuesta con Inteligencia Artificial (compatible con
  cualquier proveedor LLM vía API HTTP: OpenAI, Anthropic, Azure OpenAI,
  modelos propios, etc.).
* Configuración 100% dentro de Ajustes de Odoo: token permanente,
  Phone Number ID, Verify Token, versión de Graph API.
* SLA de primera respuesta: semáforo en vivo y aviso automático al
  agente si una conversación nueva lleva mucho tiempo sin contestarse.
* Encuesta de satisfacción (1 a 5) enviada sola al cerrar una
  conversación, con la calificación del cliente guardada en el canal.
* Catálogo de productos por WhatsApp: lista interactiva de hasta 10
  productos que el cliente puede tocar para agregarlos directo al
  carrito de la conversación, sin necesitar un Catálogo de Meta
  Commerce Manager aparte.

Requisitos
----------
* Cuenta de Meta Business + App de WhatsApp Business Platform (Cloud API).
* Token de acceso permanente (System User) con permisos
  ``whatsapp_business_messaging`` y ``whatsapp_business_management``.
* URL pública de Odoo para registrar el Webhook en Meta.
    """,

    'author': "Bryan Cando",
    'website': "https://github.com/brphoto/Prueba_Odoo",
    'license': 'LGPL-3',

    'category': 'Discuss',
    'version': '19.0.2.0.2',

    # sale/purchase/crm/account eran opcionales hasta esta versión (el
    # módulo revisaba 'modelo' in self.env por todos lados para no
    # romperse si no estaban). A partir de acá son dependencias reales:
    # el panel de contacto asume que un vendedor por WhatsApp puede
    # armar presupuestos, facturas, oportunidades y compras sin salir
    # del chat, así que tiene más sentido que este módulo traiga esas
    # apps consigo que dejarlas "si te acordás de instalarlas". Las
    # comprobaciones 'modelo in self.env' se dejaron igual en el código
    # (no estorban estando siempre instalado) por las dudas de que este
    # módulo se reuse en una instalación más liviana en el futuro.
    'depends': ['base', 'mail', 'bus', 'contacts', 'sale', 'purchase', 'crm', 'account'],

    'data': [
        'security/chatroom_security.xml',
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'views/chatroom_whatsapp_number_views.xml',
        'views/chatroom_tag_views.xml',
        'views/chatroom_new_conversation_wizard_views.xml',
        'views/chatroom_reassign_wizard_views.xml',
        'views/chatroom_template_views.xml',
        'views/chatroom_send_catalog_wizard_views.xml',
        'views/chatroom_channel_views.xml',
        'views/chatroom_metrics_views.xml',
        'views/chatroom_message_views.xml',
        'views/chatroom_scheduled_message_views.xml',
        'views/chatroom_canned_response_views.xml',
        'views/res_config_settings_views.xml',
        'views/res_partner_views.xml',
        'views/chatroom_onboarding_wizard_views.xml',
        'views/chatroom_menus.xml',
    ],

    'assets': {
        'web.assets_backend': [
            'chatroom_whatsapp/static/src/chatroom_thread/chatroom_thread_core.js',
            'chatroom_whatsapp/static/src/chatroom_thread/chatroom_thread_core.xml',
            'chatroom_whatsapp/static/src/chatroom_thread/chatroom_thread.js',
            'chatroom_whatsapp/static/src/chatroom_thread/chatroom_thread.xml',
            'chatroom_whatsapp/static/src/chatroom_thread/chatroom_thread.scss',
            'chatroom_whatsapp/static/src/systray/chatroom_systray.js',
            'chatroom_whatsapp/static/src/systray/chatroom_systray.xml',
            'chatroom_whatsapp/static/src/systray/chatroom_systray.scss',
            'chatroom_whatsapp/static/src/chatroom_app/new_conversation_dialog.js',
            'chatroom_whatsapp/static/src/chatroom_app/new_conversation_dialog.xml',
            'chatroom_whatsapp/static/src/chatroom_app/new_conversation_dialog.scss',
            'chatroom_whatsapp/static/src/chatroom_app/contact_panel.js',
            'chatroom_whatsapp/static/src/chatroom_app/contact_panel.xml',
            'chatroom_whatsapp/static/src/chatroom_app/contact_panel.scss',
            'chatroom_whatsapp/static/src/chatroom_app/chatroom_app.js',
            'chatroom_whatsapp/static/src/chatroom_app/chatroom_app.xml',
            'chatroom_whatsapp/static/src/chatroom_app/chatroom_app.scss',
            'chatroom_whatsapp/static/src/chatroom_dashboard/chatroom_dashboard.js',
            'chatroom_whatsapp/static/src/chatroom_dashboard/chatroom_dashboard.xml',
            'chatroom_whatsapp/static/src/chatroom_dashboard/chatroom_dashboard.scss',
        ],
        'web.assets_web_dark': [
            'chatroom_whatsapp/static/src/chatroom_thread/chatroom_thread.dark.scss',
            'chatroom_whatsapp/static/src/chatroom_app/chatroom_app.dark.scss',
            'chatroom_whatsapp/static/src/chatroom_app/new_conversation_dialog.dark.scss',
            'chatroom_whatsapp/static/src/chatroom_app/contact_panel.dark.scss',
            'chatroom_whatsapp/static/src/chatroom_dashboard/chatroom_dashboard.dark.scss',
        ],
    },

    'demo': [],

    'installable': True,
    'application': True,
    'auto_install': False,
}

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
    'version': '19.0.1.0.0',

    'depends': ['base', 'mail', 'bus', 'contacts'],

    'data': [
        'security/chatroom_security.xml',
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'views/chatroom_template_views.xml',
        'views/chatroom_channel_views.xml',
        'views/chatroom_metrics_views.xml',
        'views/chatroom_message_views.xml',
        'views/res_config_settings_views.xml',
        'views/res_partner_views.xml',
        'views/chatroom_menus.xml',
    ],

    'assets': {
        'web.assets_backend': [
            'chatroom_whatsapp/static/src/chatroom_thread/chatroom_thread.js',
            'chatroom_whatsapp/static/src/chatroom_thread/chatroom_thread.xml',
            'chatroom_whatsapp/static/src/chatroom_thread/chatroom_thread.scss',
        ],
    },

    'demo': [],

    'installable': True,
    'application': True,
    'auto_install': False,
}

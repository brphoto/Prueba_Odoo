# -*- coding: utf-8 -*-
{
    'name': "Chatroom - Reuniones (Calendario)",

    'summary': """
        Agrega un botón para agendar y ver reuniones (Calendario nativo
        de Odoo) desde el panel de contacto del Chatroom WhatsApp, sin
        modificarlo: módulo 100% opcional y desacoplado.""",

    'description': """
Chatroom - Reuniones (Calendario)
===================================

Extiende (sin tocar) el módulo **Chatroom WhatsApp & Redes Sociales** con
un acceso directo al **Calendario nativo de Odoo** desde el panel de
contacto, para poder agendar una reunión con el cliente sin salir del
chat.

* **Botón "Reunión"** en el panel de contacto: abre el formulario real
  de `calendar.event` (con invitaciones, videollamada, recordatorios,
  todo lo nativo de Calendario), precargado con el contacto de la
  conversación como invitado.
* **Contador de reuniones** en la fila de accesos rápidos: con una sola
  reunión agendada, abre directo su formulario; con varias, abre la
  vista de calendario/lista filtrada por el contacto.

Diseño modular
----------------
Este módulo **depende de** ``chatroom_whatsapp`` y del módulo nativo
``calendar`` de Odoo, pero ``chatroom_whatsapp`` no depende de este ni
sabe que existe: toda la integración se hace por extensión del modelo
(``chatroom.channel``) y parche de los componentes OWL existentes
(``t-inherit`` de templates + ``patch()`` de las clases JS), mismo
criterio que ya usa ``chatroom_sales_intelligence``. Desinstalar este
módulo deja el chatroom exactamente como estaba antes de instalarlo.
    """,

    'author': "Bryan Cando",
    'website': "https://github.com/brphoto/Prueba_Odoo",
    'license': 'LGPL-3',

    'category': 'Sales/CRM',
    'version': '19.0.1.0.0',

    'depends': ['chatroom_whatsapp', 'calendar'],

    'data': [],

    'assets': {
        'web.assets_backend': [
            'chatroom_calendar/static/src/chatroom_app/contact_panel_patch.js',
            'chatroom_calendar/static/src/chatroom_app/contact_panel_patch.xml',
            'chatroom_calendar/static/src/chatroom_thread/chatroom_thread_patch.js',
            'chatroom_calendar/static/src/chatroom_thread/chatroom_thread_patch.xml',
        ],
    },

    'demo': [],

    'installable': True,
    'application': False,
    'auto_install': False,
}

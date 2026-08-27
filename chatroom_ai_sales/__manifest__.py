{
    'name': 'Chatroom Ventas Autónomas',
    'summary': 'Convierte conversaciones de WhatsApp en ventas con límites y trazabilidad',
    'description': '''Capa comercial opcional para Chatroom.

Usa el catálogo y carrito existentes, exige confirmación explícita del cliente,
aplica límites de monto, confirma pedidos solo si la política lo permite y
puede enviar el enlace de pago mediante el conector instalado (incluido PayPhone).
Las ventas autónomas permanecen desactivadas hasta que el administrador las configure.''',
    'version': '19.0.1.0.2',
    'author': 'Bryan Cando',
    'license': 'LGPL-3',
    'category': 'Sales/CRM',
    'depends': ['chatroom_whatsapp', 'chatroom_ai_agent', 'sale', 'mail'],
    'data': [
        'security/chatroom_ai_sales_security.xml',
        'security/ir.model.access.csv',
        'views/chatroom_ai_sales_event_views.xml',
        'views/res_config_settings_views.xml',
        'views/chatroom_ai_sales_menus.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'icon': 'static/description/icon.svg',
    'assets': {
        'web.assets_backend': [
            'chatroom_ai_sales/static/src/chatroom_ai_sales.scss',
        ],
    },
}

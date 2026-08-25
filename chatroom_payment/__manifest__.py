{
    'name': 'Chatroom Payment Links',
    'author': 'Bryan Cando',
    'website': 'https://github.com/brphoto/Prueba_Odoo',
    'version': '19.0.1.0.4',
    'category': 'Sales/Payment',
    'summary': 'Payment-link actions from Chatroom',
    'depends': ['chatroom_whatsapp', 'payment', 'sale', 'account'],
    'data': [
        'security/chatroom_payment_security.xml',
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'views/chatroom_payment_link_wizard_views.xml',
        'views/chatroom_payment_link_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'chatroom_payment/static/src/chatroom_payment_forms.scss',
            'chatroom_payment/static/src/chatroom_thread/chatroom_thread_patch.js',
            'chatroom_payment/static/src/chatroom_thread/chatroom_thread_patch.xml',
            'chatroom_payment/static/src/chatroom_app/contact_panel_patch.js',
            'chatroom_payment/static/src/chatroom_app/contact_panel_patch.xml',
            'chatroom_payment/static/src/chatroom_app/contact_panel_patch.scss',
        ],
        'web.assets_web_dark': [
            'chatroom_payment/static/src/chatroom_app/contact_panel_patch.dark.scss',
        ],
    },
    'license': 'LGPL-3',
    'icon': '/chatroom_payment/static/description/icon.svg',
    'installable': True,
    'application': False,
    'auto_install': False,
}

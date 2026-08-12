{
    'name': 'Chatroom Payment Links',
    'version': '19.0.1.0.0',
    'category': 'Sales/Payment',
    'summary': 'Payment-link actions from Chatroom',
    'depends': ['chatroom_whatsapp', 'payment', 'sale', 'account'],
    'data': [
        'views/chatroom_payment_link_wizard_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'chatroom_payment/static/src/chatroom_thread/chatroom_thread_patch.js',
            'chatroom_payment/static/src/chatroom_thread/chatroom_thread_patch.xml',
            'chatroom_payment/static/src/chatroom_app/contact_panel_patch.js',
            'chatroom_payment/static/src/chatroom_app/contact_panel_patch.xml',
        ],
    },
    'license': 'LGPL-3',
    'icon': '/chatroom_payment/static/description/icon.svg',
    'installable': True,
    'application': False,
    'auto_install': False,
}

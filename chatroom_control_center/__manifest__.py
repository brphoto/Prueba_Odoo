{
    'name': 'Chatroom Control Center',
    'author': 'Bryan Cando',
    'website': 'https://github.com/brphoto/Prueba_Odoo',
    'version': '19.0.1.0.6',
    'category': 'Productivity/Discuss',
    'summary': 'Centro de control para las integraciones de Chatroom',
    'depends': ['chatroom_whatsapp'],
    'data': [
        'security/ir.model.access.csv',
        'views/chatroom_control_center_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'chatroom_control_center/static/src/scss/chatroom_control_center.scss',
        ],
    },
    'license': 'LGPL-3',
    'icon': '/chatroom_control_center/static/description/icon.svg',
    'installable': True,
    'application': False,
    'auto_install': True,
}

{
    'name': 'Chatroom UI Professional',
    'author': 'Bryan Cando',
    'website': 'https://github.com/brphoto/Prueba_Odoo',
    'version': '19.0.1.0.7',
    'category': 'Productivity/Discuss',
    'summary': 'Professional visual layer and responsive UX for Chatroom',
    'depends': ['chatroom_whatsapp'],
    'data': [
        'views/res_config_settings_views.xml',
        'views/res_users_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'chatroom_ui/static/src/chatroom_ui.scss',
            'chatroom_ui/static/src/chatroom_ui_settings.scss',
            'chatroom_ui/static/src/chatroom_ui_preview.js',
            'chatroom_ui/static/src/chatroom_ui_patch.js',
        ],
        'web.assets_web_dark': [
            'chatroom_ui/static/src/chatroom_ui.dark.scss',
        ],
    },
    'license': 'LGPL-3',
    'icon': '/chatroom_ui/static/description/icon.svg',
    'installable': True,
    'application': False,
    'auto_install': True,
}

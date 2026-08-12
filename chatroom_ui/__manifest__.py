{
    'name': 'Chatroom UI Professional',
    'version': '19.0.1.0.0',
    'category': 'Productivity/Discuss',
    'summary': 'Professional visual layer and responsive UX for Chatroom',
    'depends': ['chatroom_whatsapp'],
    'data': [],
    'assets': {
        'web.assets_backend': [
            'chatroom_ui/static/src/chatroom_ui.scss',
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

{
    'name': 'Chatroom IA - Modelos y Consumo',
    'summary': 'Selector de modelos y control de consumo de OpenAI Platform',
    'description': '''Modulo opcional para administrar modelos disponibles,
consumo local, costos oficiales y limites de la plataforma de IA.

No reemplaza el motor de WhatsApp ni obliga a usar OpenAI: funciona con
proveedores compatibles con los endpoints de modelos y uso.''',
    'version': '19.0.1.0.26',
    'author': 'Bryan Cando',
    'license': 'LGPL-3',
    'category': 'Discuss',
    'depends': ['chatroom_ai', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'views/chatroom_ai_usage_views.xml',
        'views/res_config_settings_views.xml',
        'views/chatroom_ai_usage_menus.xml',
        'views/ai_setup_wizard_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'assets': {
        'web.assets_backend': [
            'chatroom_ai_usage/static/src/chatroom_ai_usage.scss',
        ],
    },
}

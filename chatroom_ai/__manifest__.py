{
    'name': 'Chatroom IA controlada',
    'summary': 'Sugerencias de IA con aprobación, trazabilidad y fuentes',
    'description': '''Módulo opcional para preparar respuestas de IA sin enviarlas automáticamente.

Cada sugerencia queda como un registro auditable, con conversación de origen,
intención, confianza, estado, aprobador y fecha de envío. No reemplaza el
motor de WhatsApp ni obliga a instalar un proveedor de IA.''',
    'version': '19.0.1.1.1',
    'author': 'Bryan Cando',
    'license': 'LGPL-3',
    'category': 'Discuss',
    'depends': ['chatroom_whatsapp', 'mail'],
    'assets': {
        'web.assets_backend': [
            'chatroom_ai/static/src/chatroom_ai_assistant.js',
            'chatroom_ai/static/src/chatroom_ai_assistant.xml',
            'chatroom_ai/static/src/chatroom_ai_assistant.scss',
        ],
    },
    'data': [
        'security/chatroom_ai_security.xml',
        'security/ir.model.access.csv',
        'views/chatroom_ai_suggestion_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}

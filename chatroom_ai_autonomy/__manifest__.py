{
    'name': 'Chatroom IA - Conocimiento y Autonomía',
    'summary': 'Conocimiento operativo de Odoo y políticas de autonomía controlada',
    'description': '''Organiza las fuentes vivas de Odoo, permite simular consultas
de IA con trazabilidad y controla las acciones comerciales del agente mediante
políticas configurables y aprobación humana.''',
    'version': '19.0.1.0.2',
    'author': 'Bryan Cando',
    'license': 'LGPL-3',
    'category': 'Productivity/Discuss',
    'depends': [
        'chatroom_ai_knowledge', 'chatroom_ai_agent', 'chatroom_ai_usage',
        'chatroom_ai_sales_fulfillment', 'chatroom_ai_operations',
    ],
    'data': [
        'security/chatroom_ai_autonomy_security.xml',
        'security/ir.model.access.csv',
        'views/chatroom_ai_autonomy_views.xml',
        'views/chatroom_ai_autonomy_templates.xml',
        'views/chatroom_ai_autonomy_menus.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'icon': 'static/description/icon.svg',
}

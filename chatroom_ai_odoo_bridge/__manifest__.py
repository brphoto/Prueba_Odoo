{
    'name': 'Chatroom - Puente IA nativa de Odoo',
    'summary': 'Conecta Chatroom con la IA nativa de Odoo Enterprise de forma opcional',
    'version': '19.0.1.0.1',
    'category': 'Productivity/AI',
    'author': 'Chatroom',
    'license': 'OEEL-1',
    'depends': [
        'ai',
        'mail',
        'chatroom_ai_usage',
        'chatroom_ai_knowledge',
        'chatroom_ai_agent',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/chatroom_ai_odoo_bridge_views.xml',
    ],
    'installable': True,
    'application': False,
}

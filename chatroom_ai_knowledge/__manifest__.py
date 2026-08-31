# -*- coding: utf-8 -*-
{
    'name': 'Chatroom IA - Centro de conocimiento',
    'summary': 'Integra la base de conocimiento con el menú del Agente IA',
    'description': '''Módulo puente opcional que organiza el conocimiento
interno de Chatroom dentro del Agente IA sin mezclar la lógica comercial,
de WhatsApp o de ventas.''',
    'version': '19.0.1.0.3',
    'author': 'Bryan Cando',
    'license': 'LGPL-3',
    'category': 'Productivity/Discuss',
    'depends': ['chatroom_ai_agent', 'chatroom_sales_intelligence'],
    'data': [
        'security/ir.model.access.csv',
        'views/knowledge_menu.xml',
        'views/knowledge_test_views.xml',
        'views/knowledge_composer_views.xml',
        'views/knowledge_brain_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'chatroom_ai_knowledge/static/src/scss/chatroom_ai_knowledge.scss',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}

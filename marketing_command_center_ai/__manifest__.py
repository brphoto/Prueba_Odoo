{
    'name': 'Marketing - Consultas IA',
    'summary': 'Consultas y resúmenes de Marketing con el proveedor IA configurado',
    'description': '''Puente opcional entre el Centro de mando de Marketing y el
motor de IA de Chatroom. Conserva el análisis local y habilita consultas IA
con selector de modelo, fuentes, consumo y aprobación operativa.''',
    'version': '19.0.1.0.1',
    'author': 'Bryan Cando',
    'license': 'LGPL-3',
    'category': 'Marketing/Marketing',
    'depends': ['marketing_command_center', 'chatroom_ai_usage'],
    'data': [
        'views/marketing_command_center_ai_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}

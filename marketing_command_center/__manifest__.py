{
    'name': 'Centro de mando de marketing social',
    'summary': 'Métricas centralizadas de redes sociales y agente analítico',
    'description': '''Centro independiente para consolidar publicaciones, métricas,
interacciones y campañas de redes sociales. Incluye dashboard ejecutivo,
modo demo y un agente conversacional local que responde con datos exactos.
Los conectores de cada red y los puentes con CRM o Chatroom son opcionales.''',
    'version': '19.0.1.0.2',
    'author': 'Bryan Cando',
    'license': 'LGPL-3',
    'category': 'Marketing/Marketing',
    'depends': ['mail'],
    'data': [
        'security/marketing_command_center_security.xml',
        'security/ir.model.access.csv',
        'data/marketing_command_center_data.xml',
        'views/marketing_command_center_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'marketing_command_center/static/src/scss/marketing_command_center.scss',
        ],
    },
    'icon': 'static/description/icon.svg',
    'installable': True,
    'application': True,
    'auto_install': False,
}

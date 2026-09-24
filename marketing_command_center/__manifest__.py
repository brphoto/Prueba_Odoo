{
    'name': 'Centro de mando de marketing social',
    'summary': 'Métricas centralizadas de redes sociales y agente analítico',
    'description': '''Centro independiente para consolidar publicaciones, métricas,
interacciones y campañas de redes sociales. Incluye dashboard ejecutivo,
modo demo y un agente conversacional local que responde con datos exactos.
Los conectores de cada red y los puentes con CRM o Chatroom son opcionales.''',
    'version': '19.0.1.0.11',
    'author': 'Bryan Cando',
    'license': 'LGPL-3',
    'category': 'Marketing/Marketing',
    'depends': ['mail', 'product'],
    'data': [
        'security/marketing_command_center_security.xml',
        'security/ir.model.access.csv',
        'data/marketing_command_center_data.xml',
        'data/ir_cron_data.xml',
        'views/marketing_command_center_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'marketing_command_center/static/src/scss/marketing_command_center.scss',
        ],
        # Solo redefine colores; la maquetacion vive en el SCSS claro.
        'web.assets_web_dark': [
            'marketing_command_center/static/src/scss/marketing_command_center.dark.scss',
        ],
        # Bundle que Odoo carga solo durante los tests de navegador.
        'web.assets_tests': [
            'marketing_command_center/static/tests/tours/marketing_command_center_tour.js',
        ],
    },
    'icon': '/marketing_command_center/static/description/icon.svg',
    'installable': True,
    'application': True,
    'auto_install': False,
}

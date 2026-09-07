{
    'name': 'Marketing social - Conectores avanzados',
    'summary': 'Conecta Instagram, YouTube, LinkedIn y TikTok al Centro de mando',
    'description': '''Conectores opcionales de lectura para redes sociales.
Sincroniza cuentas, publicaciones, métricas e interacciones usando las APIs
oficiales de Instagram, YouTube, LinkedIn y TikTok.''',
    'version': '19.0.1.0.3',
    'author': 'Bryan Cando',
    'license': 'LGPL-3',
    'category': 'Marketing/Marketing',
    'depends': ['marketing_command_center'],
    'data': [
        'security/marketing_command_center_social_connectors_security.xml',
        'security/ir.model.access.csv',
        'data/marketing_command_center_social_connectors_data.xml',
        'views/marketing_command_center_social_connectors_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'marketing_command_center_social_connectors/static/src/scss/marketing_command_center_social_connectors.scss',
        ],
    },
    'icon': 'static/description/icon.svg',
    'installable': True,
    'application': False,
    'auto_install': False,
}

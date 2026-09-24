{
    'name': 'Marketing - Catálogo externo',
    'summary': 'Vehículos y catálogo externo con estados publicados y despublicados',
    'description': '''Conector opcional para centralizar un catálogo de vehículos
publicado en un portal externo. Incluye conexión configurable, importación segura
de feeds JSON, demo reproducible, fichas de vehículo, imágenes, enlaces y estados
comerciales. No está atado a ningún portal concreto: el origen de cada anuncio se
guarda en el campo «Origen».''',
    # 2.0.0 porque el modulo cambio de nombre: era
    # `marketing_command_center_patiotuerca`. El `pre_init_hook`
    # migra en sitio las bases que tenian el nombre anterior.
    'version': '19.0.2.0.0',
    'pre_init_hook': 'pre_init_hook',
    'author': 'Bryan Cando',
    'license': 'LGPL-3',
    'category': 'Marketing/Marketing',
    'depends': ['marketing_command_center', 'mail'],
    'data': [
        'security/marketing_command_center_catalog_security.xml',
        'security/ir.model.access.csv',
        'data/catalog_demo.xml',
        'views/marketing_catalog_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'marketing_command_center_catalog/static/src/scss/marketing_catalog.scss',
        ],
    },
    'icon': '/marketing_command_center_catalog/static/description/icon.svg',
    'installable': True,
    'application': False,
    'auto_install': False,
}

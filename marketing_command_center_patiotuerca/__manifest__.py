{
    'name': 'Marketing - Catálogo Patiotuerca',
    'summary': 'Vehículos y catálogo externo con estados publicados y despublicados',
    'description': '''Conector opcional para centralizar el inventario publicado en
Patiotuerca. Incluye conexión configurable, importación segura de feeds JSON,
demo reproducible, fichas de vehículo, imágenes, enlaces y estados comerciales.''',
    'version': '19.0.1.0.2',
    'author': 'Bryan Cando',
    'license': 'LGPL-3',
    'category': 'Marketing/Marketing',
    'depends': ['marketing_command_center', 'mail'],
    'data': [
        'security/marketing_command_center_patiotuerca_security.xml',
        'security/ir.model.access.csv',
        'data/patiotuerca_demo.xml',
        'views/marketing_patiotuerca_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'marketing_command_center_patiotuerca/static/src/scss/marketing_patiotuerca.scss',
        ],
    },
    'icon': 'static/description/icon.svg',
    'installable': True,
    'application': False,
    'auto_install': False,
}

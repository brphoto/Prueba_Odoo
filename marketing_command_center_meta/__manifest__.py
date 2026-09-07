{
    'name': 'Marketing social - Conector Meta',
    'summary': 'Conecta páginas reales de Facebook y sincroniza sus métricas',
    'description': '''Conector independiente para páginas de Facebook/Meta.
Permite probar credenciales, descubrir varias páginas, sincronizar publicaciones,
métricas e interacciones y conservar un historial de errores. La primera versión
es de lectura: no publica ni modifica contenido en Meta.''',
    'version': '19.0.1.0.10',
    'author': 'Bryan Cando',
    'license': 'LGPL-3',
    'category': 'Marketing/Marketing',
    'depends': ['marketing_command_center'],
    'data': [
        'security/marketing_command_center_meta_security.xml',
        'security/ir.model.access.csv',
        'data/marketing_command_center_meta_data.xml',
        'views/marketing_command_center_meta_views.xml',
    ],
    'icon': 'static/description/icon.svg',
    'installable': True,
    'application': False,
    'auto_install': False,
}

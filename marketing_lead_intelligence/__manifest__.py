{
    'name': 'Inteligencia comercial de leads',
    'summary': 'Ficha 360° de CRM con origen social y trazabilidad comercial',
    'description': '''Extiende el lead nativo de Odoo con la información comercial
de redes sociales, conversaciones, publicaciones y calidad del lead. El módulo
es opcional y no instala Chatroom, IA ni conectores de redes.''',
    'version': '19.0.1.0.2',
    'author': 'Bryan Cando',
    'license': 'LGPL-3',
    'category': 'Marketing/CRM',
    'depends': ['crm', 'mail', 'marketing_command_center'],
    'data': [
        'security/ir.model.access.csv',
        'views/crm_lead_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}

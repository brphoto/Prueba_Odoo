{
    'name': 'Históricos Comerciales para RFM',
    'summary': 'Carga históricos de compras sin crear ventas ni productos.',
    'description': '''
Históricos Comerciales
======================

Permite cargar facturas históricas desde CSV/XLSX en un módulo separado de
Ventas y Productos. Los datos aprobados alimentan RFM/ABC, conservando lote,
errores, duplicados, clientes identificados y categoría manual.
    ''',
    'author': 'Bryan Cando',
    'website': 'https://github.com/brphoto/Prueba_Odoo',
    'license': 'LGPL-3',
    'category': 'Sales/CRM',
    'version': '19.0.1.0.6',
    'depends': ['crm_customer_intelligence'],
    'data': [
        'security/crm_customer_history_security.xml',
        'security/ir.model.access.csv',
        'views/crm_customer_history_views.xml',
        'views/res_partner_views.xml',
        'views/crm_customer_history_menus.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}

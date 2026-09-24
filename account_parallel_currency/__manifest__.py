{
    'name': "Parallel Currency Accounting",
    'version': '19.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': "Moneda Paralela",
    'description': """
Moneda Paralela
""",
    'author': "Bryan Cando",
    'license': 'LGPL-3',
    'depends': ['account', 'accountant'],
    'data': [
        'views/res_company_views.xml',
        'views/account_move_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
}

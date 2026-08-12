{
    'name': 'Payment Provider: PayPhone',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Payment Providers',
    'sequence': 120,
    'summary': 'PayPhone payments for Odoo',
    'description': 'Integrates PayPhone API Sale and API Link with Odoo payment transactions.',
    'depends': ['payment'],
    'data': [
        'views/payment_provider_views.xml',
        'views/payment_payphone_templates.xml',
        'data/payment_provider_data.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
}

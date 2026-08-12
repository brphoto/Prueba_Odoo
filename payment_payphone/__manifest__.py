{
    'name': 'Payment Provider: PayPhone',
    'version': '19.0.1.0.16',
    'category': 'Accounting/Payment Providers',
    'sequence': 120,
    'summary': 'PayPhone payments for Odoo',
    'description': 'Integrates PayPhone Cajita Web, API Sale and API Link with Odoo payment transactions.',
    'depends': ['payment'],
    'data': [
        'views/payment_provider_views.xml',
        'views/payment_payphone_templates.xml',
        'data/payment_provider_data.xml',
        'data/payphone_cron.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'license': 'LGPL-3',
    'assets': {
        'web.assets_frontend': [
            'payment_payphone/static/src/interactions/payment_form.js',
        ],
    },
    'installable': True,
    'application': False,
}

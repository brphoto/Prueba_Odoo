{
    'name': 'Payment Provider: Datafast',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Payment Providers',
    'sequence': 350,
    'summary': 'Datafast Dataweb payment integration for Ecuador',
    'description': """
Datafast Dataweb payment provider for Odoo 19.

This module uses the hosted Datafast/OPPWA payment widget. Card data is entered
inside the provider widget and is never sent to Odoo.
    """,
    'depends': ['payment'],
    'data': [
        'views/payment_datafast_templates.xml',
        'views/payment_provider_views.xml',
        'views/payment_transaction_views.xml',
        'data/payment_provider_data.xml',
        'data/payment_datafast_cron.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'payment_datafast/static/src/interactions/payment_form.js',
        ],
    },
    'license': 'LGPL-3',
    'author': 'Custom',
    'icon': '/payment_datafast/static/description/icon.svg',
}

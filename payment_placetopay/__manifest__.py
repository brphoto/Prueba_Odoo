{
    'name': 'Payment Provider: PlacetoPay',
    'author': 'Bryan Cando',
    'website': 'https://github.com/brphoto/Prueba_Odoo',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Payment Providers',
    'sequence': 130,
    'summary': 'Acepta pagos con PlacetoPay Checkout (tarjeta, PSE, Baloto, Efecty y más)',
    'description': """
Integración del Web Checkout de PlacetoPay (https://docs.placetopay.dev/) con
los proveedores de pago de Odoo.

* Crea una sesión de pago vía la API REST de PlacetoPay y redirige al cliente
  a la pasarela alojada.
* Consulta el estado final de la sesión al volver del checkout y mediante un
  cron de respaldo para transacciones que quedaron pendientes.
* Soporta entorno de pruebas (sandbox) y producción con credenciales
  independientes (login + clave secreta).
    """,
    'depends': ['payment'],
    'data': [
        'views/payment_provider_views.xml',
        'views/payment_placetopay_templates.xml',
        'views/payment_transaction_views.xml',
        'data/payment_provider_data.xml',
        'data/placetopay_cron.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'license': 'LGPL-3',
    'icon': '/payment_placetopay/static/description/icon.svg',
    'installable': True,
    'application': False,
}

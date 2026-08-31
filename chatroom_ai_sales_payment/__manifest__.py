{
    'name': 'Chatroom Ventas Autónomas - Postventa de Pagos',
    'summary': 'Cierra el ciclo de pago, factura y notificación de ventas autónomas',
    'description': '''Puente opcional entre Chatroom Payment y Ventas autónomas.

Sincroniza pagos confirmados, evita duplicados, prepara facturas y notifica
al cliente. Los pasos con error quedan registrados para reintento.''',
    'version': '19.0.1.0.1',
    'author': 'Bryan Cando',
    'license': 'LGPL-3',
    'category': 'Sales/Payment',
    'depends': ['chatroom_ai_sales', 'chatroom_payment', 'account', 'sale'],
    'data': ['views/res_config_settings_views.xml'],
    'installable': True,
    'application': False,
    'auto_install': False,
}

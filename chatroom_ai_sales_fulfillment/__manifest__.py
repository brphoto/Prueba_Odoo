{
    'name': 'Chatroom Cumplimiento de Ventas',
    'summary': 'Inventario, entregas, carritos y reintentos para ventas conversacionales',
    'description': '''Capa opcional de cumplimiento para las ventas autónomas de Chatroom.

Valida inventario y datos de entrega antes de confirmar, informa el avance de los
despachos, recuerda carritos abandonados y permite reintentar enlaces fallidos
con límites configurables. No reemplaza WhatsApp, pagos ni el agente IA.''',
    'version': '19.0.1.0.3',
    'author': 'Bryan Cando',
    'license': 'LGPL-3',
    'category': 'Sales/CRM',
    'depends': ['chatroom_ai_sales_payment', 'stock', 'sale_stock', 'delivery'],
    'data': [
        'security/ir.model.access.csv',
        'views/res_config_settings_views.xml',
        'data/ir_cron_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'icon': 'static/description/icon.svg',
}

{
    "name": "Gestión de Pólizas para Partner",
    "version": "19.0.1.1.0",
    "author": "Bryan Cando",
    "category": "Tools",
    "summary": "Módulo para gestionar pólizas asociadas a un partner",
    "depends": ["base", "contacts", "crm", "sale", "purchase", "account"],
    "description": """
        Este módulo permite gestionar pólizas asociadas a un partner, incluyendo la generación de órdenes de compra y venta para liquidación de comisiones.
        Incluye funcionalidades para el manejo de recordatorios y seguimiento de pólizas.
    """,
    "data": [
        'data/sequence.xml',
        'data/cron.xml',
        "security/ir.model.access.csv",
        "views/poliza_views.xml",
        "views/res_partner_views.xml",
        "views/recordatorio_template.xml",
        "views/menu.xml",
        'views/comision_views.xml',
        'views/sale_purchase.xml',
        'views/crm.xml',
        'views/insurance_views.xml',
    ],
    "icon": "/polizas_partner/static/description/icon.svg",
    "license": "LGPL-3",
    "installable": True,
    "application": True
}

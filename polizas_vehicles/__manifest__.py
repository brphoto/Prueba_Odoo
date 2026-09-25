{
    "name": "Gestión de Pólizas para Partner (VEHICULOS)",
    "version": "19.0.1.1.0",
    "author": "Bryan Cando",
    "category": "Tools",
    "summary": "Módulo para gestionar pólizas asociadas a un partner (VEHICULOS)",
    "description": """
        Este módulo extiende la funcionalidad de gestión de pólizas para incluir vehículos.
        Permite asociar pólizas a vehículos y gestionar la información relacionada.
    """,
    "depends": ["polizas_partner"],
    "data": [
        'security/ir.model.access.csv',
        "views/poliza_views.xml",
        
    ],
    "icon": "/polizas_vehicles/static/description/icon.svg",
    "license": "LGPL-3",
    "installable": True,
    "application": True
}

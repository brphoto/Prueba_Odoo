{
    "name": "Nómina Colombia - Operación",
    "summary": "Periodos y resúmenes de nómina sin facturación electrónica",
    "description": """
        Flujo operativo simple para nómina colombiana sobre el motor estándar
        de Odoo. Permite preparar periodos, revisar recibos, consolidar totales
        por empleado y cerrar el periodo sin depender de integraciones DIAN.
    """,
    "author": "Navegasoft",
    "website": "https://www.navegasoft.com",
    "category": "Human Resources/Payroll",
    "version": "19.0.4.0.0",
    "license": "OPL-1",
    "depends": ["hr_payroll", "account"],
    "data": [
        "security/nav_nomina_security.xml",
        "security/ir.model.access.csv",
        "data/ir_sequence.xml",
        "views/nav_nomina_parameter_views.xml",
        "views/nav_nomina_novelty_views.xml",
        "views/nav_nomina_social_views.xml",
        "views/nav_nomina_adjustment_views.xml",
        "views/nav_nomina_settlement_views.xml",
        "views/nav_nomina_pila_views.xml",
        "views/nav_nomina_payment_views.xml",
        "views/nav_nomina_rule_mapping_views.xml",
        "views/nav_nomina_period_wizard_views.xml",
        "views/nav_nomina_period_views.xml",
        "views/nav_nomina_menu.xml",
        "report/nav_nomina_period_report.xml",
    ],
    "installable": True,
    "icon": "static/description/icon.svg",
    "application": True,
}

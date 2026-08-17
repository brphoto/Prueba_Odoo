{
    "name": "Nómina electrónica DIAN Colombia",
    "summary": "Generación, firma, transmisión y seguimiento de nómina electrónica ante la DIAN",
    "description": """
        Extensión opcional para transmitir el documento soporte de pago de nómina electrónica
        y sus notas de ajuste a la DIAN, integrada con los periodos y cálculos de nómina colombiana.
    """,
    "author": "Bryan Cando",
    "category": "Human Resources/Payroll",
    "version": "19.0.4.0.0",
    "license": "OPL-1",
    "depends": ["l10n_co_payroll", "certificate"],
    "external_dependencies": {"python": ["cryptography", "lxml", "signxml", "requests"]},
    "assets": {
        "web.assets_backend": [
            "l10n_co_payroll_dian/static/src/scss/dian_ui.scss",
        ],
    },
    "data": [
        "security/ir.model.access.csv",
        "data/ir_sequence.xml",
        "data/ir_cron.xml",
        "views/dian_company_views.xml",
        "views/dian_document_views.xml",
        "views/dian_period_views.xml",
        "views/dian_payslip_views.xml",
        "views/dian_dashboard_views.xml",
        "views/dian_rule_mapping_views.xml",
        "views/dian_menu.xml",
    ],
    "installable": True,
    "application": False,
}

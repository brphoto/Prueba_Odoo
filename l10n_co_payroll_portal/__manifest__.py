{
    "name": "Nómina Colombia - Portal",
    "summary": "Portal profesional y opcional para colaboradores",
    "version": "19.0.2.1.0",
    "category": "Human Resources/Payroll",
    "author": "Bryan Cando",
    "license": "OPL-1",
    "depends": ["l10n_co_payroll", "portal", "website", "hr_holidays"],
    "data": [
        "security/ir.model.access.csv",
        "security/security.xml",
        "views/portal_templates.xml",
        "views/access_log_views.xml",
        "views/request_views.xml",
        "report/payslip_report.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "l10n_co_payroll_portal/static/src/css/payroll_portal.css",
        ],
    },
    "installable": True,
    "application": False,
}

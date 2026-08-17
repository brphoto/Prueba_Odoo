from . import models
from . import wizard


def post_init_hook(env):
    """Seed a usable 2026 Colombian legal version for companies without one."""
    Parameter = env["l10n.co.payroll.parameter"].sudo()
    for company in env["res.company"].sudo().search([]):
        if Parameter.search([("company_id", "=", company.id), ("year", "=", 2026)], limit=1):
            continue
        Parameter.create({
            "company_id": company.id,
            "year": 2026,
            "version": 1,
            "effective_from": "2026-01-01",
            "effective_to": "2026-12-31",
            "status": "active",
            "minimum_wage": 1750905.0,
            "transport_allowance": 249095.0,
            "holiday_rate": 90.0,
            "source_reference": "UGPP Calculadora IBC / Decreto 1470 de 2025 / Ley 2466 de 2025",
            "legal_basis": "Versión inicial parametrizable para 2026. Revisar y aprobar anualmente con la norma vigente.",
        })

from . import models
from . import wizard


def _get_or_create(env, model_name, domain, values):
    model = env[model_name].sudo()
    record = model.search(domain, limit=1)
    return record or model.create(values)


def _ensure_colombian_structures(env):
    """Create Colombian salary structures independently of pay frequency.

    Ordinary/integral define the salary treatment and rules. Monthly,
    biweekly, weekly and extraordinary define the payroll period and belong
    to ``l10n.co.payroll.period.period_type``.
    """
    StructureType = env["hr.payroll.structure.type"].sudo()
    Structure = env["hr.payroll.structure"].sudo()
    country = env.ref("base.co", raise_if_not_found=False)
    definitions = [
        ("CO_ORDINARIA", "Nómina colombiana ordinaria", "monthly", "Estructura de reglas para salario ordinario. La frecuencia se selecciona en el periodo."),
        ("CO_INTEGRAL", "Nómina colombiana salario integral", "monthly", "Estructura de reglas para salario integral. La frecuencia se selecciona en el periodo."),
    ]
    legacy_monthly = Structure.search([("code", "=", "CO_MENSUAL")], limit=1)
    if legacy_monthly and not Structure.search([("code", "=", "CO_ORDINARIA")], limit=1):
        legacy_monthly.write({"code": "CO_ORDINARIA"})
    structures = Structure.browse()
    for code, name, schedule, note in definitions:
        structure_type = StructureType.search([("name", "=", name)], limit=1)
        if not structure_type:
            structure_type = StructureType.create({
                "name": name,
                "default_schedule_pay": schedule,
                "wage_type": "monthly",
            })
        structure = Structure.search([("code", "=", code)], limit=1)
        if not structure:
            values = {
                "name": name,
                "code": code,
                "type_id": structure_type.id,
                "note": note,
                "payslip_name": name,
            }
            if country:
                values["country_id"] = country.id
            structure = Structure.create(values)
        else:
            structure.write({
                "name": name,
                "type_id": structure_type.id,
                "note": note,
                "payslip_name": name,
                "active": True,
            })
        if not structure_type.default_struct_id:
            structure_type.default_struct_id = structure.id
        structures |= structure

    # Previous versions modeled the frequency as a structure. Reusing the
    # monthly record as ordinary preserves links from historical payslips;
    # the other frequency records remain archived for historical traceability.
    legacy_ordinary = Structure.search([("code", "=", "CO_MENSUAL")], limit=1)
    ordinary = structures.filtered(lambda record: record.code == "CO_ORDINARIA")
    if legacy_ordinary and ordinary and legacy_ordinary != ordinary:
        legacy_ordinary.write({
            "active": False,
            "note": "Estructura histórica archivada. La frecuencia se configura en el tipo de periodo.",
        })
    elif legacy_ordinary and not ordinary:
        legacy_ordinary.write({
            "code": "CO_ORDINARIA",
            "name": "Nómina colombiana ordinaria",
            "note": "Estructura de reglas para salario ordinario. La frecuencia se selecciona en el periodo.",
            "payslip_name": "Nómina colombiana ordinaria",
            "active": True,
        })
        structures |= legacy_ordinary

    Structure.search([("code", "in", ["CO_QUINCENAL", "CO_SEMANAL"])]).write({
        "active": False,
        "note": "Estructura histórica archivada. La frecuencia se configura en el tipo de periodo.",
    })
    return structures


def _ensure_colombian_input_types(env, structures):
    InputType = env["hr.payslip.input.type"].sudo()
    country = env.ref("base.co", raise_if_not_found=False)
    definitions = [
        ("HED", "Horas extra diurnas", True),
        ("HEN", "Horas extra nocturnas", True),
        ("HDF", "Horas dominicales o festivas", True),
        ("RN", "Horas de recargo nocturno", True),
        ("COMISION", "Comisiones salariales", False),
        ("BONO_SAL", "Bonificación salarial", False),
        ("BONO_NOSAL", "Bonificación no salarial", False),
        ("RETENCION", "Retención en la fuente", False),
        ("EMBARGO", "Embargo judicial", False),
        ("ANTICIPO", "Anticipo de nómina", False),
        ("PRESTAMO", "Cuota de préstamo", False),
        ("OTRAS_DED", "Otras deducciones autorizadas", False),
        ("VAC_PAGADA", "Pago de vacaciones", False),
        ("INCAPACIDAD", "Incapacidad reconocida", False),
        ("LIC_MAT", "Licencia de maternidad", False),
        ("LIC_PAT", "Licencia de paternidad", False),
        ("LIC_REM", "Licencia remunerada", False),
        ("AUSENCIA", "Ausencia no remunerada", False),
        ("PRIMA_PAGO", "Pago de prima de servicios", False),
        ("CESANTIA_PAGO", "Pago de cesantías", False),
        ("INTERES_CESANT", "Pago de intereses de cesantías", False),
        ("REINTEGRO", "Reintegro o reembolso", False),
    ]
    for code, name, is_quantity in definitions:
        record = InputType.search([("code", "=", code)], limit=1)
        values = {"name": name, "code": code, "is_quantity": is_quantity, "struct_ids": [(6, 0, structures.ids)]}
        if country:
            values["country_id"] = country.id
        if record:
            record.write({"struct_ids": [(6, 0, structures.ids)]})
        else:
            InputType.create(values)


def _ensure_colombian_rules(env, parameter, structures):
    Rule = env["l10n.co.payroll.salary.rule"].sudo()
    definitions = [
        (1, "Auxilio de transporte", "AUX_TRANSP", "earning", "add", "worked_days > 0 and salary_mode == 'ordinary' and basic_wage <= minimum_wage * legal('transport_allowance_max_wage_multiple')", "transport_allowance * worked_days / 30.0", "Se reconoce hasta el tope de SMLMV configurado y se prorratea por días trabajados."),
        (2, "Hora extra diurna", "HED", "earning", "add", "source('HED') > 0", "source('HED') * basic_wage / (legal('weekly_hours') * 5.0) * (1.0 + legal('overtime_day_rate') / 100.0)", "Horas reportadas como cantidad. Divisor: jornada semanal por cinco, según parametrización."),
        (3, "Hora extra nocturna", "HEN", "earning", "add", "source('HEN') > 0", "source('HEN') * basic_wage / (legal('weekly_hours') * 5.0) * (1.0 + legal('overtime_night_rate') / 100.0)", "Horas reportadas como cantidad."),
        (4, "Hora dominical o festiva", "HDF", "earning", "add", "source('HDF') > 0", "source('HDF') * basic_wage / (legal('weekly_hours') * 5.0) * (1.0 + legal('holiday_rate') / 100.0)", "Incluye el valor de la hora y el recargo vigente parametrizado."),
        (5, "Recargo nocturno", "RN", "earning", "add", "source('RN') > 0", "source('RN') * basic_wage / (legal('weekly_hours') * 5.0) * legal('night_rate') / 100.0", "Recargo sobre la hora ordinaria; las horas se reportan como cantidad."),
        (6, "Comisiones salariales", "COMISION", "earning", "add", "source('COMISION') > 0", "source('COMISION')", "Valor monetario reportado en la entrada de nómina."),
        (7, "Bonificación salarial", "BONO_SAL", "earning", "add", "source('BONO_SAL') > 0", "source('BONO_SAL')", "Concepto salarial sujeto a IBC según su naturaleza."),
        (8, "Bonificación no salarial", "BONO_NOSAL", "earning", "add", "source('BONO_NOSAL') > 0", "source('BONO_NOSAL')", "Se muestra como devengado, pero no se incluye automáticamente en el IBC."),
        (9, "IBC legal", "IBC_BASE", "ibc", "replace", "basic_wage > 0", "basic_wage + rule('HED') + rule('HEN') + rule('HDF') + rule('RN') + rule('COMISION') + rule('BONO_SAL')", "Base salarial preliminar; después se normaliza entre el mínimo, el 70% integral y el tope de 25 SMLMV."),
        (10, "Salud a cargo del colaborador", "SALUD_EMP", "employee_contribution", "add", "rule('IBC_BASE') > 0", "rule('IBC_BASE') * legal('health_employee_rate') / 100.0", "Aporte obligatorio del colaborador."),
        (11, "Pensión a cargo del colaborador", "PENSION_EMP", "employee_contribution", "add", "rule('IBC_BASE') > 0", "rule('IBC_BASE') * legal('pension_employee_rate') / 100.0", "Aporte obligatorio del colaborador."),
        (12, "Fondo de solidaridad pensional", "FSP", "employee_contribution", "add", "rule('IBC_BASE') >= minimum_wage * legal('solidarity_threshold_mw')", "rule('IBC_BASE') * solidarity_rate / 100.0", "Aporte progresivo según el IBC y los rangos legales configurados."),
        (13, "Retención en la fuente", "RETENCION", "deduction", "add", "legal('withholding_enabled') and (source('RETENCION') > 0 or legal('withholding_value') > 0)", "source('RETENCION') if source('RETENCION') > 0 else legal('withholding_value')", "Cálculo base por UVT según el artículo 383 del Estatuto Tributario; la entrada manual permite sustituir el valor cuando exista soporte del procedimiento aplicable."),
        (14, "Embargo judicial", "EMBARGO", "deduction", "add", "source('EMBARGO') > 0", "source('EMBARGO')", "Deducción reportada conforme a la orden judicial."),
        (15, "Anticipo de nómina", "ANTICIPO", "deduction", "add", "source('ANTICIPO') > 0", "source('ANTICIPO')", "Deducción autorizada por el colaborador."),
        (16, "Cuota de préstamo", "PRESTAMO", "deduction", "add", "source('PRESTAMO') > 0", "source('PRESTAMO')", "Deducción de cuota vigente."),
        (17, "Otras deducciones autorizadas", "OTRAS_DED", "deduction", "add", "source('OTRAS_DED') > 0", "source('OTRAS_DED')", "Deducción reportada con soporte."),
        (18, "Salud a cargo del empleador", "SALUD_EMPRESA", "employer_contribution", "add", "rule('IBC_BASE') > 0", "0.0 if legal('employer_health_exempt') else rule('IBC_BASE') * legal('health_employer_rate') / 100.0", "Aporte patronal; la exoneración se activa solo con soporte legal de la compañía."),
        (19, "Pensión a cargo del empleador", "PENSION_EMPRESA", "employer_contribution", "add", "rule('IBC_BASE') > 0", "rule('IBC_BASE') * legal('pension_employer_rate') / 100.0", "Aporte patronal obligatorio."),
        (20, "ARL", "ARL", "employer_contribution", "add", "rule('IBC_BASE') > 0", "rule('IBC_BASE') * legal('arl_rate') / 100.0", "Tarifa inicial según clase de riesgo del perfil PILA."),
        (21, "Caja de compensación familiar", "CCF", "employer_contribution", "add", "rule('IBC_BASE') > 0", "rule('IBC_BASE') * legal('ccf_rate') / 100.0", "Aporte patronal a caja de compensación."),
        (22, "SENA", "SENA", "employer_contribution", "add", "rule('IBC_BASE') > 0", "0.0 if legal('employer_sena_exempt') else rule('IBC_BASE') * legal('sena_rate') / 100.0", "Aporte parafiscal sujeto a las condiciones legales de exoneración."),
        (23, "ICBF", "ICBF", "employer_contribution", "add", "rule('IBC_BASE') > 0", "0.0 if legal('employer_icbf_exempt') else rule('IBC_BASE') * legal('icbf_rate') / 100.0", "Aporte parafiscal sujeto a las condiciones legales de exoneración."),
        (24, "Provisión de cesantías", "PROV_CESANT", "provision", "add", "worked_days > 0", "gross_wage * legal('severance_rate') / 100.0", "Provisión contable mensual; no es un descuento al colaborador."),
        (25, "Provisión de intereses de cesantías", "PROV_INT_CESANT", "provision", "add", "worked_days > 0", "gross_wage * legal('severance_interest_rate') / 100.0 * worked_days / 360.0", "Provisión contable referencial; el pago anual se liquida sobre las cesantías causadas y la tasa legal parametrizada."),
        (26, "Provisión de vacaciones", "PROV_VAC", "provision", "add", "worked_days > 0", "basic_wage * legal('vacation_rate') / 100.0", "Provisión contable mensual."),
        (27, "Provisión de prima", "PROV_PRIMA", "provision", "add", "worked_days > 0", "gross_wage * legal('bonus_rate') / 100.0", "Provisión contable mensual."),
        (28, "Pago de vacaciones", "VAC_PAGADA", "earning", "add", "source('VAC_PAGADA') > 0", "source('VAC_PAGADA')", "Entrada monetaria para vacaciones pagadas o compensadas; validar el tratamiento según el caso."),
        (29, "Incapacidad reconocida", "INCAPACIDAD", "earning", "add", "source('INCAPACIDAD') > 0", "source('INCAPACIDAD')", "Entrada monetaria con soporte de incapacidad y entidad responsable."),
        (30, "Licencia de maternidad", "LIC_MAT", "earning", "add", "source('LIC_MAT') > 0", "source('LIC_MAT')", "Entrada monetaria con soporte de licencia de maternidad."),
        (31, "Licencia de paternidad", "LIC_PAT", "earning", "add", "source('LIC_PAT') > 0", "source('LIC_PAT')", "Entrada monetaria con soporte de licencia de paternidad."),
        (32, "Licencia remunerada", "LIC_REM", "earning", "add", "source('LIC_REM') > 0", "source('LIC_REM')", "Entrada monetaria de licencia remunerada."),
        (33, "Ausencia no remunerada", "AUSENCIA", "deduction", "add", "source('AUSENCIA') > 0", "source('AUSENCIA')", "Deducción monetaria previamente aprobada."),
        (34, "Prima de servicios pagada", "PRIMA_PAGO", "earning", "add", "source('PRIMA_PAGO') > 0", "source('PRIMA_PAGO')", "Pago extraordinario de prima; el cálculo automático se controla desde la liquidación de prestaciones."),
        (35, "Cesantías pagadas", "CESANTIA_PAGO", "earning", "add", "source('CESANTIA_PAGO') > 0", "source('CESANTIA_PAGO')", "Pago extraordinario de cesantías; conservar soporte."),
        (36, "Intereses de cesantías pagados", "INTERES_CESANT", "earning", "add", "source('INTERES_CESANT') > 0", "source('INTERES_CESANT')", "Pago extraordinario de intereses de cesantías."),
        (37, "Reintegro o reembolso", "REINTEGRO", "earning", "add", "source('REINTEGRO') > 0", "source('REINTEGRO')", "Reintegro no salarial sujeto a soporte y tratamiento tributario."),
    ]
    for sequence, name, code, concept_type, impact, condition, formula, description in definitions:
        rule = Rule.search([("parameter_id", "=", parameter.id), ("code", "=", code)], limit=1)
        if not rule:
            Rule.create({
                "name": name,
                "company_id": parameter.company_id.id,
                "parameter_id": parameter.id,
                "sequence": sequence,
                "code": code,
                "concept_type": concept_type,
                "impact": impact,
                "condition": condition,
                "amount_expression": formula,
                "description": description,
                "is_system_default": True,
                "validation_state": "valid",
            })
        elif rule.is_system_default:
            rule.write({
                "name": name,
                "sequence": sequence,
                "concept_type": concept_type,
                "impact": impact,
                "condition": condition,
                "amount_expression": formula,
                "description": description,
                "active": True,
            })
    parameter.salary_rule_ids._ensure_native_rules(structures)
    parameter.salary_rule_ids.action_validate_formula()


def _ensure_colombian_mappings(env, parameter):
    Mapping = env["l10n.co.payroll.rule.mapping"].sudo()
    definitions = [
        ("BASIC", "Salario básico", "earning", "SAL", True, "basico"),
        ("GROSS", "Devengado base", "earning", "DEV", False, False),
        ("AUX_TRANSP", "Auxilio de transporte", "earning", "AUX", False, "auxilio_transporte"),
        ("HED", "Hora extra diurna", "earning", "HED", True, "hed_pago"),
        ("HEN", "Hora extra nocturna", "earning", "HEN", True, "hen_pago"),
        ("HDF", "Hora dominical o festiva", "earning", "HDF", True, "heddf_pago"),
        ("RN", "Recargo nocturno", "earning", "RN", True, "hrn_pago"),
        ("COMISION", "Comisiones salariales", "earning", "COM", True, "comision"),
        ("BONO_SAL", "Bonificación salarial", "earning", "BON", True, "auxilio_s"),
        ("BONO_NOSAL", "Bonificación no salarial", "earning", "BON_NS", False, "auxilio_ns"),
        ("IBC_BASE", "IBC legal", "ibc", "IBC", True, False),
        ("DED", "Deducciones", "deduction", "DED", False, False),
        ("COMP", "Aportes empresa", "employer", "COMP", False, False),
        ("SALUD_EMP", "Salud empleado", "deduction", "SALUD", False, "salud"),
        ("PENSION_EMP", "Pensión empleado", "deduction", "PENSION", False, "pension"),
        ("FSP", "Fondo de solidaridad pensional", "deduction", "FSP", False, "fsp"),
        ("RETENCION", "Retención en la fuente", "deduction", "RET", False, "retencion_fuente"),
        ("EMBARGO", "Embargo judicial", "deduction", "EMB", False, "embargo_fiscal"),
        ("PRESTAMO", "Cuota de préstamo", "deduction", "PRESTAMO", False, "deuda"),
        ("VAC_PAGADA", "Pago de vacaciones", "earning", "VAC", False, "vacaciones_pago"),
        ("INCAPACIDAD", "Incapacidad reconocida", "earning", "IGE", False, "incapacidad_comun_pago"),
        ("LIC_MAT", "Licencia de maternidad", "earning", "LMA", False, "licencia_mp_pago"),
        ("LIC_PAT", "Licencia de paternidad", "earning", "LMP", False, "licencia_mp_pago"),
        ("LIC_REM", "Licencia remunerada", "earning", "LIC", False, "licencia_r_pago"),
        ("PRIMA_PAGO", "Prima de servicios pagada", "earning", "PRIMA", False, "primas_pago"),
        ("CESANTIA_PAGO", "Cesantías pagadas", "earning", "CES", False, "cesantias_pago"),
        ("INTERES_CESANT", "Intereses de cesantías pagados", "earning", "INT_CES", False, "intereses_cesantias"),
        ("REINTEGRO", "Reintegro o reembolso", "earning", "REINTEGRO", False, "reintegro"),
    ]
    has_dian = "dian_concept" in Mapping._fields
    for code, name, concept_type, pila_code, include_in_ibc, dian_concept in definitions:
        mapping = Mapping.search([("parameter_id", "=", parameter.id), ("code", "=", code), ("concept_type", "=", concept_type)], limit=1)
        if not mapping:
            values = {
                "name": name,
                "company_id": parameter.company_id.id,
                "parameter_id": parameter.id,
                "code": code,
                "concept_type": concept_type,
                "pila_code": pila_code,
                "include_in_ibc": include_in_ibc,
                "notes": "Catálogo inicial colombiano; revisa el anexo técnico y el operador PILA antes de producción.",
            }
            if has_dian and dian_concept:
                values["dian_concept"] = dian_concept
            Mapping.create(values)
        elif has_dian and dian_concept and not mapping.dian_concept:
            mapping.write({"dian_concept": dian_concept})


def _ensure_colombian_pila(env, company):
    Config = env["l10n.co.payroll.pila.config"].sudo()
    if not Config.search([("company_id", "=", company.id)], limit=1):
        Config.create({
            "name": "PILA Colombia - archivo configurable",
            "company_id": company.id,
            "operator": "generic",
            "file_format": "csv",
            "delimiter": ";",
            "encoding": "cp1252",
            "include_header": False,
            "filename_prefix": "PILA_COLOMBIA",
            "legal_reference": "Resolución 467 de 2025 y anexo técnico PILA vigente. Validar el formato del operador antes de transmitir.",
        })


def _ensure_colombian_withholding(env, parameter):
    Bracket = env["l10n.co.payroll.withholding.bracket"].sudo()
    if not Bracket.search([("parameter_id", "=", parameter.id)], limit=1):
        Bracket.default_brackets(parameter)


def post_init_hook(env):
    """Carga idempotente de una base colombiana utilizable y versionada."""
    Parameter = env["l10n.co.payroll.parameter"].sudo()
    structures = _ensure_colombian_structures(env)
    _ensure_colombian_input_types(env, structures)
    for company in env["res.company"].sudo().search([]):
        parameter = Parameter.search([("company_id", "=", company.id), ("year", "=", 2026)], order="version desc", limit=1)
        if not parameter:
            parameter = Parameter.create({
                "company_id": company.id,
                "year": 2026,
                "version": 1,
                "effective_from": "2026-01-01",
                "effective_to": "2026-12-31",
                "status": "active",
                "minimum_wage": 1750905.0,
                "transport_allowance": 249095.0,
                "uvt_value": 52374.0,
                "weekly_hours": 42.0,
                "night_start_hour": 19.0,
                "holiday_rate": 90.0,
                "source_reference": "Decreto 0159 de 2026, Decreto 1470 de 2025, Resolución DIAN 000238 de 2025 y UGPP 2026",
                "legal_basis": "Versión inicial parametrizable. La empresa debe revisar la vigencia, su exoneración de aportes, procedimiento de retención y entidades antes de liquidar nómina real.",
            })
        else:
            blank_updates = {}
            if not parameter.uvt_value:
                blank_updates["uvt_value"] = 52374.0
            if not parameter.source_reference:
                blank_updates["source_reference"] = "Decreto 0159 de 2026, Decreto 1470 de 2025, Resolución DIAN 000238 de 2025 y UGPP 2026"
            if blank_updates:
                parameter.write(blank_updates)
        _ensure_colombian_rules(env, parameter, structures)
        _ensure_colombian_mappings(env, parameter)
        _ensure_colombian_withholding(env, parameter)
        _ensure_colombian_pila(env, company)

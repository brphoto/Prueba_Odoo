from copy import deepcopy
from decimal import Decimal, ROUND_HALF_EVEN
from pathlib import Path

from lxml import etree


MODULE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = MODULE_DIR / "dian_assets" / "templates"

NS = {
    "ext": "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
}
NOMINA_VERSION = "V1.0: Documento Soporte de Pago de N\u00f3mina Electr\u00f3nica"
NOMINA_AJUSTE_VERSION = "V1.0: Nota de Ajuste de Documento Soporte de Pago de N\u00f3mina Electr\u00f3nica"
COUNTRY_NUMERIC_CODES = {
    "CO": "170",
    "US": "840",
    "MX": "484",
    "PA": "591",
    "EC": "218",
    "PE": "604",
    "VE": "862",
}


def _bool_str(value):
    return "true" if str(value).lower() in ("1", "true", "t", "si", "sí") else "false"


def _str(value, default=""):
    if value in (None, False):
        return default
    if isinstance(value, str) and value.strip().lower() in {"false", "none", "null"}:
        return default
    return str(value).strip()


def _decimal(value, default="0.00"):
    if value is None or value is False or value == "":
        return default
    try:
        return str(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN))
    except Exception:
        return default


def _int(value, default="0"):
    if value in (None, False, ""):
        return default
    try:
        return str(int(float(value)))
    except Exception:
        return default


def _country_numeric(value, default="170"):
    raw = _str(value, "").strip().upper()
    if raw.isdigit():
        return raw[-3:].zfill(3)
    return COUNTRY_NUMERIC_CODES.get(raw[:2], default)


def _country_alpha2(value, default="CO"):
    raw = _str(value, "").strip().upper()
    if not raw:
        return default
    if raw.isdigit():
        normalized = raw[-3:].zfill(3)
        for alpha2, numeric in COUNTRY_NUMERIC_CODES.items():
            if numeric == normalized:
                return alpha2
        return default
    return raw[:2]


def _date(value, default="1900-01-01"):
    if not value:
        return default
    if isinstance(value, str) and value.strip().lower() in {"false", "none", "null"}:
        return default
    return str(value)


def _datetime(value, default="1900-01-01T00:00:00"):
    if not value:
        return default
    if isinstance(value, str) and value.strip().lower() in {"false", "none", "null"}:
        return default
    return str(value)


def _text(node, xpath, value):
    target = _xpath(node, xpath)
    if target:
        target[0].text = value


def _attrs(node, xpath, values):
    target = _xpath(node, xpath)
    if target:
        for key, value in values.items():
            target[0].set(key, value)


def _remove_xpath(node, xpath):
    targets = _xpath(node, xpath)
    for target in targets:
        parent = target.getparent()
        if parent is not None:
            parent.remove(target)


def _remove_empty_attributes(node, xpath, attributes):
    targets = _xpath(node, xpath)
    if not targets:
        return
    target = targets[0]
    for attr in attributes:
        value = target.get(attr)
        if value in ("", "0", "0.0", "0.00", "0.000"):
            target.attrib.pop(attr, None)


def _remove_attribute(node, xpath, attribute):
    targets = _xpath(node, xpath)
    if not targets:
        return
    targets[0].attrib.pop(attribute, None)


def _remove_attributes(node, xpath, attributes):
    for attribute in attributes:
        _remove_attribute(node, xpath, attribute)


def _all_zero(*values):
    return all(_decimal(value) == "0.00" for value in values)


def _prune_empty_optional_nodes(root, base_xpath):
    empty_values = {
        "",
        "0",
        "0.0",
        "0.00",
        "0.000",
        "1900-01-01",
        "1900-01-01T00:00:00",
        "9999-12-31",
        "9999-12-31T00:00:00",
        "false",
    }
    optional_xpaths = [
        f"{base_xpath}/Devengados/HEDs/HED",
        f"{base_xpath}/Devengados/HENs/HEN",
        f"{base_xpath}/Devengados/HRNs/HRN",
        f"{base_xpath}/Devengados/HEDDFs/HEDDF",
        f"{base_xpath}/Devengados/HRDDFs/HRDDF",
        f"{base_xpath}/Devengados/HENDFs/HENDF",
        f"{base_xpath}/Devengados/HRNDFs/HRNDF",
        f"{base_xpath}/Devengados/Vacaciones/VacacionesComunes",
        f"{base_xpath}/Devengados/Vacaciones/VacacionesCompensadas",
        f"{base_xpath}/Devengados/Primas",
        f"{base_xpath}/Devengados/Cesantias",
        f"{base_xpath}/Devengados/Incapacidades/Incapacidad",
        f"{base_xpath}/Devengados/Licencias/LicenciaMP",
        f"{base_xpath}/Devengados/Licencias/LicenciaR",
        f"{base_xpath}/Devengados/Licencias/LicenciaNR",
        f"{base_xpath}/Devengados/Bonificaciones/Bonificacion",
        f"{base_xpath}/Devengados/Auxilios/Auxilio",
        f"{base_xpath}/Devengados/HuelgasLegales/HuelgaLegal",
        f"{base_xpath}/Devengados/OtrosConceptos/OtroConcepto",
        f"{base_xpath}/Devengados/Compensaciones/Compensacion",
        f"{base_xpath}/Devengados/BonoEPCTVs/BonoEPCTV",
        f"{base_xpath}/Devengados/Comisiones/Comision",
        f"{base_xpath}/Devengados/PagosTerceros/PagoTercero",
        f"{base_xpath}/Devengados/Anticipos/Anticipo",
        f"{base_xpath}/Devengados/Dotacion",
        f"{base_xpath}/Devengados/ApoyoSost",
        f"{base_xpath}/Devengados/Teletrabajo",
        f"{base_xpath}/Devengados/BonifRetiro",
        f"{base_xpath}/Devengados/Indemnizacion",
        f"{base_xpath}/Devengados/Reintegro",
        f"{base_xpath}/Deducciones/Sindicatos/Sindicato",
        f"{base_xpath}/Deducciones/Sanciones/Sancion",
        f"{base_xpath}/Deducciones/Libranzas/Libranza",
        f"{base_xpath}/Deducciones/PagosTerceros/PagoTercero",
        f"{base_xpath}/Deducciones/Anticipos/Anticipo",
        f"{base_xpath}/Deducciones/OtrasDeducciones/OtraDeduccion",
        f"{base_xpath}/Deducciones/PensionVoluntaria",
        f"{base_xpath}/Deducciones/FondoSP",
        f"{base_xpath}/Deducciones/RetencionFuente",
        f"{base_xpath}/Deducciones/AFC",
        f"{base_xpath}/Deducciones/Cooperativa",
        f"{base_xpath}/Deducciones/EmbargoFiscal",
        f"{base_xpath}/Deducciones/PlanComplementarios",
        f"{base_xpath}/Deducciones/Educacion",
        f"{base_xpath}/Deducciones/Reintegro",
        f"{base_xpath}/Deducciones/Deuda",
    ]
    wrapper_xpaths = [
        f"{base_xpath}/Devengados/HEDs",
        f"{base_xpath}/Devengados/HENs",
        f"{base_xpath}/Devengados/HRNs",
        f"{base_xpath}/Devengados/HEDDFs",
        f"{base_xpath}/Devengados/HRDDFs",
        f"{base_xpath}/Devengados/HENDFs",
        f"{base_xpath}/Devengados/HRNDFs",
        f"{base_xpath}/Devengados/Comisiones",
        f"{base_xpath}/Devengados/Vacaciones",
        f"{base_xpath}/Devengados/Incapacidades",
        f"{base_xpath}/Devengados/Licencias",
        f"{base_xpath}/Devengados/Bonificaciones",
        f"{base_xpath}/Devengados/Auxilios",
        f"{base_xpath}/Devengados/HuelgasLegales",
        f"{base_xpath}/Devengados/OtrosConceptos",
        f"{base_xpath}/Devengados/Compensaciones",
        f"{base_xpath}/Devengados/BonoEPCTVs",
        f"{base_xpath}/Devengados/PagosTerceros",
        f"{base_xpath}/Devengados/Anticipos",
        f"{base_xpath}/Deducciones/Sindicatos",
        f"{base_xpath}/Deducciones/Sanciones",
        f"{base_xpath}/Deducciones/Libranzas",
        f"{base_xpath}/Deducciones/PagosTerceros",
        f"{base_xpath}/Deducciones/Anticipos",
        f"{base_xpath}/Deducciones/OtrasDeducciones",
    ]

    for xpath in optional_xpaths:
        for target in _xpath(root, xpath):
            text_value = (target.text or "").strip()
            attr_values = [(value or "").strip() for value in target.attrib.values()]
            if text_value and text_value not in empty_values:
                continue
            if any(value not in empty_values for value in attr_values):
                continue
            parent = target.getparent()
            if parent is not None:
                parent.remove(target)

    for xpath in wrapper_xpaths:
        for target in _xpath(root, xpath):
            has_children = any(isinstance(child.tag, str) for child in target)
            has_text = bool((target.text or "").strip())
            if not has_children and not has_text:
                parent = target.getparent()
                if parent is not None:
                    parent.remove(target)


def _local_name_xpath(xpath):
    parts = []
    for part in xpath.split("/"):
        if not part:
            parts.append("")
            continue
        if part in (".", "..") or part.startswith("@") or "(" in part or ":" in part:
            parts.append(part)
            continue
        predicate = ""
        name = part
        if "[" in part:
            name, predicate = part.split("[", 1)
            predicate = "[" + predicate
        parts.append(f"*[local-name()='{name}']{predicate}")
    return "/".join(parts)


def _xpath(node, xpath):
    result = node.xpath(xpath, namespaces=NS)
    if result:
        return result
    return node.xpath(_local_name_xpath(xpath), namespaces=NS)


def _load_template(is_adjustment):
    template_name = (
        "Nomina Individual De Ajuste Electronica V1.0.2.xml"
        if is_adjustment
        else "Nomina Individual Electronica V1.0.2.xml"
    )
    tree = etree.parse(str(TEMPLATES_DIR / template_name))
    return deepcopy(tree.getroot())


def _ensure_signature_container(root):
    extensions = root.find(".//{urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2}UBLExtensions")
    if extensions is None:
        return
    extension = extensions.find(".//{urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2}UBLExtension")
    if extension is None:
        extension = etree.SubElement(extensions, f"{{{NS['ext']}}}UBLExtension")
    content = extension.find(".//{urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2}ExtensionContent")
    if content is None:
        etree.SubElement(extension, f"{{{NS['ext']}}}ExtensionContent")


def build_nomina_xml(data):
    payload = data["payload"]
    record = data["record"]
    xml_categories = data.get("xml_categories", {})
    dev = xml_categories.get("devengados", data.get("devengados", {}))
    ded = xml_categories.get("deducciones", data.get("deducciones", {}))
    root = _load_template(data["is_adjustment"])
    _ensure_signature_container(root)

    schema_location = (
        "dian:gov:co:facturaelectronica:NominaIndividualDeAjuste NominaIndividualDeAjusteElectronicaXSD.xsd"
        if data["is_adjustment"]
        else "dian:gov:co:facturaelectronica:NominaIndividual NominaIndividualElectronicaXSD.xsd"
    )
    root.set("SchemaLocation", schema_location)
    root.set("{http://www.w3.org/2001/XMLSchema-instance}schemaLocation", schema_location)

    base_xpath = "/NominaIndividualDeAjuste/Reemplazar" if data["is_adjustment"] else "/NominaIndividual"
    if not data["is_adjustment"]:
        _remove_xpath(root, "/NominaIndividual/Novedad")
    else:
        tipo_nota = _int(data["tipo_nota"], "1")
        _text(root, "/NominaIndividualDeAjuste/TipoNota", tipo_nota)
        if tipo_nota == "1":
            _remove_xpath(root, "/NominaIndividualDeAjuste/Eliminar")
        else:
            _remove_xpath(root, "/NominaIndividualDeAjuste/Reemplazar")
        _attrs(
            root,
            "/NominaIndividualDeAjuste/Reemplazar/ReemplazandoPredecesor",
            {
                "NumeroPred": _str(payload.get("NumeroPred"), "0"),
                "CUNEPred": _str(payload.get("CUNEPred"), "0"),
                "FechaGenPred": _date(payload.get("FechaGenPred")),
            },
        )

    _attrs(
        root,
        f"{base_xpath}/Periodo",
        {
            "FechaIngreso": _date(data["fecha_ingreso"]),
            "FechaLiquidacionInicio": _date(data["fecha_liquidacion_inicio"]),
            "FechaLiquidacionFin": _date(data["fecha_liquidacion_fin"]),
            "TiempoLaborado": _str(data["tiempo_laborado"], "0"),
            "FechaGen": _date(data["meta"]["fecha_gen"]),
        },
    )
    if data.get("fecha_retiro"):
        _attrs(
            root,
            f"{base_xpath}/Periodo",
            {"FechaRetiro": _date(data["fecha_retiro"])},
        )
    else:
        _remove_attribute(root, f"{base_xpath}/Periodo", "FechaRetiro")
    _attrs(
        root,
        f"{base_xpath}/NumeroSecuenciaXML",
        {
            "CodigoTrabajador": _str(data["codigo_trabajador"], "0"),
            "Prefijo": _str(data["meta"]["prefix"], ""),
            "Consecutivo": _str(data["meta"]["consecutivo"], "0"),
            "Numero": _str(data["meta"]["numero_completo"], "0"),
        },
    )
    _attrs(
        root,
        f"{base_xpath}/LugarGeneracionXML",
        {
            "Pais": _str(payload.get("paisgeneracion") or payload.get("PaisEmpleador"), "CO"),
            "DepartamentoEstado": _str(
                payload.get("departamentoestado") or payload.get("DepartamentoEstadoEmpleador"), "11"
            ),
            "MunicipioCiudad": _str(
                payload.get("municipiociudad") or payload.get("MunicipioCiudadEmpleador"), "11001"
            ),
            "Idioma": _str(payload.get("Idioma"), "es"),
        },
    )
    _attrs(
        root,
        f"{base_xpath}/ProveedorXML",
        {
            "RazonSocial": _str(payload.get("RazonSocial"), "NA"),
            "PrimerApellido": _str(payload.get("PrimerApellido"), "NA"),
            "SegundoApellido": _str(payload.get("SegundoApellido"), "NA"),
            "PrimerNombre": _str(payload.get("PrimerNombre"), "NA"),
            "OtrosNombres": _str(payload.get("OtrosNombres"), ""),
            "NIT": _int(payload.get("NIT")),
            "DV": _int(payload.get("DV")),
            "SoftwareID": _str(data["software_id"], "NA"),
            "SoftwareSC": _str(data.get("software_security_code"), "NA"),
        },
    )
    if _str(payload.get("RazonSocial"), "").strip():
        _remove_attributes(
            root,
            f"{base_xpath}/ProveedorXML",
            ["PrimerApellido", "SegundoApellido", "PrimerNombre", "OtrosNombres"],
        )
    _text(root, f"{base_xpath}/CodigoQR", _str(data["codigo_qr"], data["cune"]))
    _attrs(
        root,
        f"{base_xpath}/InformacionGeneral",
        {
            "Version": NOMINA_AJUSTE_VERSION if data["is_adjustment"] else NOMINA_VERSION,
            "Ambiente": _str(data["meta"]["ambiente"], "2"),
            "TipoXML": _str(data["tipo_xml"], "102"),
            "CUNE": _str(data["cune"], "NA"),
            "EncripCUNE": "CUNE-SHA384",
            "FechaGen": _date(data["meta"]["fecha_gen"]),
            "HoraGen": _str(data["meta"]["hora_gen"], "00:00:00-05:00"),
            "PeriodoNomina": _str(payload.get("PeriodoNomina"), "5"),
            "TipoMoneda": _str(payload.get("TipoMoneda"), "COP"),
            "TRM": _decimal(data.get("trm"), "0"),
        },
    )
    notes = _str(payload.get("Notas"), "").strip()
    if notes:
        _text(root, f"{base_xpath}/Notas", notes)
    else:
        _remove_xpath(root, f"{base_xpath}/Notas")
    _attrs(
        root,
        f"{base_xpath}/Empleador",
        {
            "RazonSocial": _str(payload.get("RazonSocial"), "NA"),
            "PrimerApellido": _str(payload.get("PrimerApellido"), "NA"),
            "SegundoApellido": _str(payload.get("SegundoApellido"), "NA"),
            "PrimerNombre": _str(payload.get("PrimerNombre"), "NA"),
            "OtrosNombres": _str(payload.get("OtrosNombres"), ""),
            "NIT": _int(payload.get("NIT")),
            "DV": _int(payload.get("DV")),
            "Pais": _str(payload.get("PaisEmpleador"), "CO"),
            "DepartamentoEstado": _str(payload.get("DepartamentoEstadoEmpleador"), "11"),
            "MunicipioCiudad": _str(payload.get("MunicipioCiudadEmpleador"), "11001"),
            "Direccion": _str(payload.get("DireccionEmpleador"), "NA"),
        },
    )
    if _str(payload.get("RazonSocial"), "").strip():
        _remove_attributes(
            root,
            f"{base_xpath}/Empleador",
            ["PrimerApellido", "SegundoApellido", "PrimerNombre", "OtrosNombres"],
        )
    _attrs(
        root,
        f"{base_xpath}/Trabajador",
        {
            "TipoTrabajador": _str(data["tipo_trabajador"], "01"),
            "SubTipoTrabajador": _str(data["sub_tipo_trabajador"], "00"),
            "AltoRiesgoPension": _bool_str(data["alto_riesgo_pension"]),
            "TipoDocumento": _str(data["tipo_documento"], "13"),
            "NumeroDocumento": _str(data["numero_documento"], "0"),
            "PrimerApellido": _str(data["primer_apellido"], "NA"),
            "SegundoApellido": _str(data["segundo_apellido"], ""),
            "PrimerNombre": _str(data["primer_nombre"], "NA"),
            "OtrosNombres": _str(data["otros_nombres"], "NA"),
            "LugarTrabajoPais": _country_alpha2(data["lugar_trabajo_pais"]),
            "LugarTrabajoDepartamentoEstado": _str(data["lugar_trabajo_departamento"], "11"),
            "LugarTrabajoMunicipioCiudad": _str(data["lugar_trabajo_municipio"], "11001"),
            "LugarTrabajoDireccion": _str(data["lugar_trabajo_direccion"], "NA"),
            "SalarioIntegral": _bool_str(data["salario_integral"]),
            "TipoContrato": _str(data["tipo_contrato"], "2"),
            "Sueldo": _decimal(data["sueldo"], "0"),
            "CodigoTrabajador": _str(data["codigo_trabajador"], "0"),
        },
    )
    _attrs(
        root,
        f"{base_xpath}/Pago",
        {
            "Forma": _str(data["forma_pago"], "1"),
            "Metodo": _str(data["metodo_pago"], "10"),
            "Banco": _str(data["banco"], ""),
            "TipoCuenta": _str(data["tipo_cuenta"], ""),
            "NumeroCuenta": _str(data["numero_cuenta"], ""),
        },
    )
    _text(root, f"{base_xpath}/FechasPagos/FechaPago", _date(data["fecha_pago"]))

    _attrs(
        root,
        f"{base_xpath}/Devengados/Basico",
        {
            "DiasTrabajados": _int(data["dias_trabajados"]),
            "SueldoTrabajado": _decimal(dev.get("basico") or data["sueldo"]),
        },
    )
    _attrs(
        root,
        f"{base_xpath}/Devengados/Transporte",
        {
            "AuxilioTransporte": _decimal(dev.get("auxilio_transporte")),
            "ViaticoManuAlojS": _decimal(dev.get("viatico_manu_aloj_s")),
            "ViaticoManuAlojNS": _decimal(dev.get("viatico_manu_aloj_ns")),
        },
    )
    hora_inicio = _datetime(f"{_date(data['fecha_liquidacion_inicio'], '1900-01-01')}T00:00:00")
    hora_fin = _datetime(f"{_date(data['fecha_liquidacion_fin'], '1900-01-01')}T00:00:00")
    extra_hour_types = [
        ("HEDs/HED", "hed"),
        ("HENs/HEN", "hen"),
        ("HRNs/HRN", "hrn"),
        ("HEDDFs/HEDDF", "heddf"),
        ("HRDDFs/HRDDF", "hrddf"),
        ("HENDFs/HENDF", "hendf"),
        ("HRNDFs/HRNDF", "hrndf"),
    ]
    for node_path, prefix in extra_hour_types:
        _attrs(
            root,
            f"{base_xpath}/Devengados/{node_path}",
            {
                "HoraInicio": _datetime(dev.get(f"{prefix}_hora_inicio"), hora_inicio),
                "HoraFin": _datetime(dev.get(f"{prefix}_hora_fin"), hora_fin),
                "Cantidad": _int(dev.get(f"{prefix}_cantidad")),
                "Porcentaje": _decimal(dev.get(f"{prefix}_porcentaje")),
                "Pago": _decimal(dev.get(f"{prefix}_pago")),
            },
        )
    _attrs(
        root,
        f"{base_xpath}/Devengados/Vacaciones/VacacionesComunes",
        {
            "FechaInicio": _date(data["fecha_liquidacion_inicio"], "1900-01-01"),
            "FechaFin": _date(data["fecha_liquidacion_fin"], "1900-01-01"),
            "Cantidad": _int(dev.get("vacaciones_cantidad")),
            "Pago": _decimal(dev.get("vacaciones_pago")),
        },
    )
    _attrs(
        root,
        f"{base_xpath}/Devengados/Primas",
        {
            "Cantidad": _int(dev.get("primas_cantidad")),
            "Pago": _decimal(dev.get("primas_pago")),
            "PagoNS": _decimal(dev.get("primas_pago_ns")),
        },
    )
    _attrs(
        root,
        f"{base_xpath}/Devengados/Cesantias",
        {
            "Pago": _decimal(dev.get("cesantias_pago")),
            "Porcentaje": _decimal(dev.get("cesantias_porcentaje")),
            "PagoIntereses": _decimal(dev.get("intereses_cesantias")),
        },
    )
    _attrs(
        root,
        f"{base_xpath}/Devengados/Auxilios/Auxilio",
        {
            "AuxilioS": _decimal(dev.get("auxilio_s")),
            "AuxilioNS": _decimal(dev.get("auxilio_ns")),
        },
    )
    license_specs = (
        ("LicenciaMP", "licencia_mp"),
        ("LicenciaR", "licencia_r"),
    )
    for node_name, prefix in license_specs:
        _attrs(
            root,
            f"{base_xpath}/Devengados/Licencias/{node_name}",
            {
                "FechaInicio": _date(dev.get(f"{prefix}_fecha_inicio")),
                "FechaFin": _date(dev.get(f"{prefix}_fecha_fin")),
                "Cantidad": _int(dev.get(f"{prefix}_cantidad")),
                "Pago": _decimal(dev.get(f"{prefix}_pago")),
            },
        )
    _attrs(
        root,
        f"{base_xpath}/Devengados/Licencias/LicenciaNR",
        {
            "FechaInicio": _date(dev.get("licencia_nr_fecha_inicio")),
            "FechaFin": _date(dev.get("licencia_nr_fecha_fin")),
            "Cantidad": _int(dev.get("licencia_nr_cantidad")),
        },
    )
    incapacity_specs = (
        ("incapacidad_comun_cantidad", "incapacidad_comun_pago", "1"),
        ("incapacidad_profesional_cantidad", "incapacidad_profesional_pago", "2"),
        ("incapacidad_laboral_cantidad", "incapacidad_laboral_pago", "3"),
    )
    incapacity_template = _xpath(root, f"{base_xpath}/Devengados/Incapacidades/Incapacidad")
    if incapacity_template:
        incapacity_template = incapacity_template[0]
        incapacity_parent = incapacity_template.getparent()
        rendered_incapacities = []
        for quantity_key, payment_key, incapacity_type in incapacity_specs:
            quantity = _int(dev.get(quantity_key))
            payment = _decimal(dev.get(payment_key))
            if _all_zero(quantity, payment):
                continue
            node = deepcopy(incapacity_template)
            _attrs(
                node,
                ".",
                {
                    "FechaInicio": _date(dev.get(f"{quantity_key}_fecha_inicio")),
                    "FechaFin": _date(dev.get(f"{quantity_key}_fecha_fin")),
                    "Cantidad": quantity,
                    "Tipo": incapacity_type,
                    "Pago": payment,
                },
            )
            # Never send the template sentinel date.  If the source payroll
            # line has no date, omit the optional attributes instead.
            if not dev.get(f"{quantity_key}_fecha_inicio"):
                node.attrib.pop("FechaInicio", None)
            if not dev.get(f"{quantity_key}_fecha_fin"):
                node.attrib.pop("FechaFin", None)
            rendered_incapacities.append(node)
        if rendered_incapacities:
            incapacity_parent.remove(incapacity_template)
            for node in rendered_incapacities:
                incapacity_parent.append(node)
    _attrs(
        root,
        f"{base_xpath}/Devengados/OtrosConceptos/OtroConcepto",
        {
            "DescripcionConcepto": _str(dev.get("otro_concepto_descripcion"), ""),
            "ConceptoS": _decimal(dev.get("otro_concepto_s")),
            "ConceptoNS": _decimal(dev.get("otro_concepto_ns")),
        },
    )
    _text(root, f"{base_xpath}/Devengados/Comisiones/Comision", _decimal(dev.get("comision")))
    _text(root, f"{base_xpath}/Devengados/Dotacion", _decimal(dev.get("dotacion")))
    _text(root, f"{base_xpath}/Devengados/ApoyoSost", _decimal(dev.get("apoyo_sost")))
    _text(root, f"{base_xpath}/Devengados/Teletrabajo", _decimal(dev.get("teletrabajo")))
    _text(root, f"{base_xpath}/Devengados/BonifRetiro", _decimal(dev.get("bonif_retiro")))
    _text(root, f"{base_xpath}/Devengados/Indemnizacion", _decimal(dev.get("indemnizacion")))
    _text(root, f"{base_xpath}/Devengados/Reintegro", _decimal(dev.get("reintegro")))

    _attrs(
        root,
        f"{base_xpath}/Deducciones/Salud",
        {
            "Porcentaje": _decimal(ded.get("salud_porcentaje")),
            "Deduccion": _decimal(ded.get("salud")),
        },
    )
    _attrs(
        root,
        f"{base_xpath}/Deducciones/FondoPension",
        {
            "Porcentaje": _decimal(ded.get("pension_porcentaje")),
            "Deduccion": _decimal(ded.get("pension")),
        },
    )
    _attrs(
        root,
        f"{base_xpath}/Deducciones/FondoSP",
        {
            "Porcentaje": _decimal(ded.get("fsp_porcentaje")),
            "DeduccionSP": _decimal(ded.get("fsp")),
            "PorcentajeSub": _decimal(ded.get("fsp_sub_porcentaje")),
            "DeduccionSub": _decimal(ded.get("fsp_sub")),
        },
    )
    _text(
        root,
        f"{base_xpath}/Deducciones/RetencionFuente",
        _decimal(ded.get("retencion_fuente")),
    )
    _text(root, f"{base_xpath}/Deducciones/AFC", _decimal(ded.get("afc")))
    _text(
        root,
        f"{base_xpath}/Deducciones/Cooperativa",
        _decimal(ded.get("cooperativa")),
    )
    _text(
        root,
        f"{base_xpath}/Deducciones/EmbargoFiscal",
        _decimal(ded.get("embargo_fiscal")),
    )
    _text(
        root,
        f"{base_xpath}/Deducciones/PlanComplementarios",
        _decimal(ded.get("plan_complementarios")),
    )
    _text(root, f"{base_xpath}/Deducciones/Educacion", _decimal(ded.get("educacion")))
    _text(root, f"{base_xpath}/Deducciones/Reintegro", _decimal(ded.get("reintegro")))
    _text(root, f"{base_xpath}/Deducciones/Deuda", _decimal(ded.get("deuda")))
    _attrs(
        root,
        f"{base_xpath}/Deducciones/Sindicatos/Sindicato",
        {
            "Porcentaje": _decimal(ded.get("sindicato_porcentaje")),
            "Deduccion": _decimal(ded.get("sindicato")),
        },
    )
    _attrs(
        root,
        f"{base_xpath}/Deducciones/Sanciones/Sancion",
        {
            "SancionPublic": _decimal(ded.get("sancion_publica")),
            "SancionPriv": _decimal(ded.get("sancion_privada")),
        },
    )
    _attrs(
        root,
        f"{base_xpath}/Deducciones/Libranzas/Libranza",
        {
            "Descripcion": _str(ded.get("libranza_descripcion"), ""),
            "Deduccion": _decimal(ded.get("libranza")),
        },
    )
    _text(root, f"{base_xpath}/Deducciones/OtrasDeducciones/OtraDeduccion", _decimal(ded.get("otra_deduccion")))
    _text(root, f"{base_xpath}/Deducciones/PensionVoluntaria", _decimal(ded.get("pension_voluntaria")))

    redondeo_val = data.get("redondeo")
    if redondeo_val and float(redondeo_val) != 0:
        _text(root, f"{base_xpath}/Redondeo", _decimal(redondeo_val))
    else:
        _remove_xpath(root, f"{base_xpath}/Redondeo")
    _text(root, f"{base_xpath}/DevengadosTotal", _decimal(data["totals"]["devengados_total"]))
    _text(root, f"{base_xpath}/DeduccionesTotal", _decimal(data["totals"]["deducciones_total"]))
    _text(root, f"{base_xpath}/ComprobanteTotal", _decimal(data["totals"]["comprobante_total"]))
    _remove_empty_attributes(
        root,
        f"{base_xpath}/Devengados/Transporte",
        ["AuxilioTransporte", "ViaticoManuAlojS", "ViaticoManuAlojNS"],
    )
    _remove_empty_attributes(
        root,
        f"{base_xpath}/Devengados/Auxilios/Auxilio",
        ["AuxilioS", "AuxilioNS"],
    )
    _remove_empty_attributes(
        root,
        f"{base_xpath}/Devengados/OtrosConceptos/OtroConcepto",
        ["ConceptoS", "ConceptoNS"],
    )
    _remove_empty_attributes(
        root,
        f"{base_xpath}/Devengados/Primas",
        ["PagoNS"],
    )
    for wrapper, prefix in [("HEDs", "hed"), ("HENs", "hen"), ("HRNs", "hrn"),
                             ("HEDDFs", "heddf"), ("HRDDFs", "hrddf"),
                             ("HENDFs", "hendf"), ("HRNDFs", "hrndf")]:
        if _all_zero(dev.get(f"{prefix}_cantidad"), dev.get(f"{prefix}_pago")):
            _remove_xpath(root, f"{base_xpath}/Devengados/{wrapper}")
    if _all_zero(dev.get("otro_concepto_s"), dev.get("otro_concepto_ns")):
        _remove_xpath(root, f"{base_xpath}/Devengados/OtrosConceptos")
    if _all_zero(ded.get("fsp"), ded.get("fsp_sub")):
        _remove_xpath(root, f"{base_xpath}/Deducciones/FondoSP")
    if _all_zero(
        dev.get("auxilio_transporte"),
        dev.get("viatico_manu_aloj_s"),
        dev.get("viatico_manu_aloj_ns"),
    ):
        _remove_xpath(root, f"{base_xpath}/Devengados/Transporte")
    _prune_empty_optional_nodes(root, base_xpath)

    xml_bytes = etree.tostring(root, encoding="UTF-8", xml_declaration=True, pretty_print=True)
    # lxml may render xsi:schemaLocation as xs:schemaLocation when both xs and
    # xsi map to the same namespace URI.  DIAN requires the xsi prefix.  Fix
    # the serialized bytes BEFORE signing so the canonical form is correct.
    # lxml may render xsi:schemaLocation as xs:schemaLocation when both xs and
    # xsi map to the same URI.  DIAN example uses xsi:schemaLocation.  Fix the
    # bytes BEFORE signing so the canonical form matches.
    xml_bytes = xml_bytes.replace(b' xs:schemaLocation=', b' xsi:schemaLocation=', 1)
    return xml_bytes

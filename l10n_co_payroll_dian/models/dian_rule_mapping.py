from odoo import api, fields, models


# Código jurídico estable -> nodo DIAN. El código de la regla de Odoo solo es
# un dato de compatibilidad; la relación salary_rule_id es la que manda.
DEFAULT_DIAN_MAPPINGS = (
    ("BASIC", "Salario básico", "earning", "SAL", True, "basico"),
    ("AUX_TRANSP", "Auxilio de transporte", "earning", "AUX", False, "auxilio_transporte"),
    ("HED", "Hora extra diurna", "earning", "HED", True, "hed_pago"),
    ("HEN", "Hora extra nocturna", "earning", "HEN", True, "hen_pago"),
    ("HDF", "Hora dominical o festiva", "earning", "HDF", True, "heddf_pago"),
    ("RN", "Recargo nocturno", "earning", "RN", True, "hrn_pago"),
    ("COMISION", "Comisiones salariales", "earning", "COM", True, "comision"),
    ("BONO_SAL", "Bonificación salarial", "earning", "BON", True, "auxilio_s"),
    ("BONO_NOSAL", "Bonificación no salarial", "earning", "BON_NS", False, "auxilio_ns"),
    ("SALUD_EMP", "Salud a cargo del colaborador", "deduction", "SALUD", False, "salud"),
    ("PENSION_EMP", "Pensión a cargo del colaborador", "deduction", "PENSION", False, "pension"),
    ("FSP", "Fondo de solidaridad pensional", "deduction", "FSP", False, "fsp"),
    ("RETENCION", "Retención en la fuente", "deduction", "RET", False, "retencion_fuente"),
    ("EMBARGO", "Embargo judicial", "deduction", "EMB", False, "embargo_fiscal"),
    ("ANTICIPO", "Anticipo de nómina", "deduction", "ANTICIPO", False, "deuda"),
    ("PRESTAMO", "Cuota de préstamo", "deduction", "PRESTAMO", False, "deuda"),
    ("OTRAS_DED", "Otras deducciones autorizadas", "deduction", "OTRA_DED", False, "otra_deduccion"),
    ("VAC_PAGADA", "Pago de vacaciones", "earning", "VAC", False, "vacaciones_pago"),
    ("INCAPACIDAD", "Incapacidad reconocida", "earning", "IGE", False, "incapacidad_comun_pago"),
    ("LIC_MAT", "Licencia de maternidad", "earning", "LMA", False, "licencia_mp_pago"),
    ("LIC_PAT", "Licencia de paternidad", "earning", "LMP", False, "licencia_mp_pago"),
    ("LIC_REM", "Licencia remunerada", "earning", "LIC", False, "licencia_r_pago"),
    ("PRIMA_PAGO", "Prima de servicios pagada", "earning", "PRIMA", False, "primas_pago"),
    ("CESANTIA_PAGO", "Cesantías pagadas", "earning", "CES", False, "cesantias_pago"),
    ("INTERES_CESANT", "Intereses de cesantías pagados", "earning", "INT_CES", False, "intereses_cesantias"),
    ("REINTEGRO", "Reintegro o reembolso", "earning", "REINTEGRO", False, "reintegro"),
    ("AUSENCIA", "Ausencia no remunerada", "deduction", "AUSENCIA", False, "otra_deduccion"),
    # Bases, aportes patronales y provisiones se conservan en PILA y contabilidad.
    ("GROSS", "Devengado base", "earning", "DEV", False, False),
    ("IBC_BASE", "IBC legal", "ibc", "IBC", True, False),
    ("SALUD_EMPRESA", "Salud a cargo del empleador", "employer", "SALUD_EMPRESA", False, False),
    ("PENSION_EMPRESA", "Pensión a cargo del empleador", "employer", "PENSION_EMPRESA", False, False),
    ("ARL", "ARL", "employer", "ARL", False, False),
    ("CCF", "Caja de compensación familiar", "employer", "CCF", False, False),
    ("SENA", "SENA", "employer", "SENA", False, False),
    ("ICBF", "ICBF", "employer", "ICBF", False, False),
    ("PROV_CESANT", "Provisión de cesantías", "provision", "PROV_CES", False, False),
    ("PROV_INT_CESANT", "Provisión de intereses de cesantías", "provision", "PROV_INT_CES", False, False),
    ("PROV_VAC", "Provisión de vacaciones", "provision", "PROV_VAC", False, False),
    ("PROV_PRIMA", "Provisión de prima", "provision", "PROV_PRIMA", False, False),
)


class CoPayrollDianRuleMapping(models.Model):
    _inherit = "l10n.co.payroll.rule.mapping"

    dian_concept = fields.Selection([
        ("basico", "Básico"),
        ("auxilio_transporte", "Auxilio de transporte"),
        ("viatico_manu_aloj_s", "Viáticos salariales"),
        ("viatico_manu_aloj_ns", "Viáticos no salariales"),
        ("primas_pago", "Prima de servicios"),
        ("primas_pago_ns", "Prima no salarial"),
        ("vacaciones_pago", "Vacaciones"),
        ("cesantias_pago", "Cesantías"),
        ("intereses_cesantias", "Intereses de cesantías"),
        ("comision", "Comisiones"),
        ("dotacion", "Dotación"),
        ("apoyo_sost", "Apoyo de sostenimiento"),
        ("teletrabajo", "Auxilio de teletrabajo"),
        ("bonif_retiro", "Bonificación por retiro"),
        ("indemnizacion", "Indemnización"),
        ("reintegro", "Reintegro devengado"),
        ("auxilio_s", "Auxilio salarial"),
        ("auxilio_ns", "Auxilio no salarial"),
        ("licencia_mp_pago", "Licencia de maternidad o paternidad"),
        ("licencia_r_pago", "Licencia remunerada"),
        ("incapacidad_comun_pago", "Incapacidad común"),
        ("incapacidad_profesional_pago", "Incapacidad profesional"),
        ("incapacidad_laboral_pago", "Incapacidad laboral"),
        ("hed_pago", "Hora extra diurna"),
        ("hen_pago", "Hora extra nocturna"),
        ("hrn_pago", "Recargo nocturno"),
        ("heddf_pago", "Hora extra diurna festiva"),
        ("hrddf_pago", "Recargo diurno festivo"),
        ("hendf_pago", "Hora extra nocturna festiva"),
        ("hrndf_pago", "Recargo nocturno festivo"),
        ("salud", "Salud empleado"),
        ("pension", "Pensión empleado"),
        ("fsp", "Fondo de solidaridad pensional"),
        ("retencion_fuente", "Retención en la fuente"),
        ("afc", "AFC"),
        ("cooperativa", "Cooperativa"),
        ("sindicato", "Sindicato"),
        ("sancion", "Sanciones"),
        ("libranza", "Libranzas"),
        ("pension_voluntaria", "Pensión voluntaria"),
        ("plan_complementarios", "Planes complementarios"),
        ("educacion", "Educación"),
        ("reintegro_deduccion", "Reintegro de deducción"),
        ("embargo_fiscal", "Embargo"),
        ("deuda", "Préstamo o deuda"),
        ("otra_deduccion", "Otra deducción"),
    ], string="Concepto DIAN", help="Indica a qué nodo DIAN se lleva el valor de esta regla salarial.")
    dian_notes = fields.Text(string="Notas DIAN")
    mapping_origin = fields.Selection([
        ("linked", "Regla vinculada"),
        ("native", "Regla nativa"),
        ("legacy", "Código compatible"),
    ], string="Asignación", compute="_compute_mapping_origin")

    @api.onchange("salary_rule_id")
    def _onchange_dian_salary_rule_id(self):
        """Propose the legal DIAN concept for standard payroll rules."""
        definitions = {item[0]: item for item in DEFAULT_DIAN_MAPPINGS}
        for mapping in self:
            rule = mapping.salary_rule_id
            if not rule:
                continue
            definition = definitions.get(rule.code)
            if not definition:
                continue
            mapping.name = rule.name
            mapping.code = rule.code
            mapping.concept_type = definition[2]
            mapping.pila_code = definition[3]
            mapping.include_in_ibc = definition[4]
            mapping.dian_concept = definition[5]

    def _compute_mapping_origin(self):
        for mapping in self:
            if mapping.salary_rule_id:
                mapping.mapping_origin = "linked"
            elif mapping.native_rule_id:
                mapping.mapping_origin = "native"
            else:
                mapping.mapping_origin = "legacy"

    @api.model
    def _resolve_for_payroll_line(self, line, mappings=None):
        """Resolve a payroll line without relying on its current code."""
        if mappings is None:
            parameter = line.period_line_id.period_id.parameter_id
            mappings = self.search([
                ("company_id", "=", line.company_id.id),
                ("parameter_id", "=", parameter.id),
                ("active", "=", True),
            ])
        native_rule = getattr(line, "salary_rule_id", False)
        configured_rule = getattr(native_rule, "co_payroll_rule_id", False)
        if configured_rule:
            match = mappings.filtered(lambda item: item.salary_rule_id == configured_rule).sorted(key=lambda item: (item.priority, item.id))[:1]
            if match:
                return match
        if native_rule:
            match = mappings.filtered(lambda item: item.native_rule_id == native_rule).sorted(key=lambda item: (item.priority, item.id))[:1]
            if match:
                return match
        codes = {
            str(value).upper()
            for value in (
                getattr(line, "code", False),
                getattr(native_rule, "code", False),
                getattr(configured_rule, "code", False),
            )
            if value
        }
        return mappings.filtered(lambda item: item.code and item.code.upper() in codes).sorted(key=lambda item: (item.priority, item.id))[:1]

    @api.model
    def _sync_default_dian_mappings(self, companies=None):
        """Create/update the legal catalog while preserving manual overrides."""
        companies = companies or self.env["res.company"].search([])
        Parameter = self.env["l10n.co.payroll.parameter"].sudo()
        Rule = self.env["l10n.co.payroll.salary.rule"].sudo()
        NativeRule = self.env["hr.salary.rule"].sudo()
        Mapping = self.sudo()
        parameters = Parameter.search([("company_id", "in", companies.ids), ("active", "=", True)])
        for parameter in parameters:
            for code, name, concept_type, pila_code, include_in_ibc, dian_concept in DEFAULT_DIAN_MAPPINGS:
                rule = Rule.search([("parameter_id", "=", parameter.id), ("code", "=", code)], limit=1)
                native_rule = NativeRule.search([("code", "=", code)], order="id", limit=1)
                mapping = Mapping.search([
                    ("parameter_id", "=", parameter.id),
                    ("code", "=", code),
                    ("concept_type", "=", concept_type),
                ], limit=1)
                values = {
                    "name": name,
                    "company_id": parameter.company_id.id,
                    "parameter_id": parameter.id,
                    "code": code,
                    "concept_type": concept_type,
                    "pila_code": pila_code,
                    "include_in_ibc": include_in_ibc,
                    "salary_rule_id": rule.id if rule else False,
                    "native_rule_id": native_rule.id if native_rule and not rule else False,
                    "is_system_default": True,
                }
                if not mapping:
                    mapping = Mapping.create(values)
                else:
                    update = {key: value for key, value in values.items() if key != "dian_concept"}
                    if mapping.is_system_default or not mapping.salary_rule_id:
                        mapping.write(update)
                if dian_concept and (mapping.is_system_default or not mapping.dian_concept):
                    mapping.write({"dian_concept": dian_concept})
        return True

    def action_sync_dian_mappings(self):
        companies = self.mapped("company_id") or self.env.company
        self._sync_default_dian_mappings(companies=companies)
        return {"type": "ir.actions.client", "tag": "soft_reload"}

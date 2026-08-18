from odoo.tests import TransactionCase, tagged

from ..models.co_payroll_salary_rule import _evaluate_configured_rules


@tagged("post_install", "-at_install")
class TestColombianCatalog(TransactionCase):
    """Cobertura de catálogo: estructuras, entradas, reglas y límites legales."""

    EXPECTED_STRUCTURES = {"CO_ORDINARIA", "CO_INTEGRAL"}
    EXPECTED_INPUTS = {
        "HED", "HEN", "HDF", "RN", "COMISION", "BONO_SAL", "BONO_NOSAL", "RETENCION",
        "EMBARGO", "ANTICIPO", "PRESTAMO", "OTRAS_DED", "VAC_PAGADA", "INCAPACIDAD",
        "LIC_MAT", "LIC_PAT", "LIC_REM", "AUSENCIA", "PRIMA_PAGO", "CESANTIA_PAGO",
        "INTERES_CESANT", "REINTEGRO",
    }
    EXPECTED_RULES = {
        "AUX_TRANSP", "HED", "HEN", "HDF", "RN", "COMISION", "BONO_SAL", "BONO_NOSAL",
        "IBC_BASE", "SALUD_EMP", "PENSION_EMP", "FSP", "RETENCION", "EMBARGO", "ANTICIPO",
        "PRESTAMO", "OTRAS_DED", "SALUD_EMPRESA", "PENSION_EMPRESA", "ARL", "CCF", "SENA",
        "ICBF", "PROV_CESANT", "PROV_INT_CESANT", "PROV_VAC", "PROV_PRIMA", "VAC_PAGADA",
        "INCAPACIDAD", "LIC_MAT", "LIC_PAT", "LIC_REM", "AUSENCIA", "PRIMA_PAGO",
        "CESANTIA_PAGO", "INTERES_CESANT", "REINTEGRO",
    }

    def setUp(self):
        super().setUp()
        self.parameter = self.env["l10n.co.payroll.parameter"].search([
            ("company_id", "=", self.env.company.id),
            ("year", "=", 2026),
        ], order="version desc", limit=1)
        self.assertTrue(self.parameter, "La instalación debe cargar la vigencia legal predeterminada.")

    def test_default_structures_inputs_rules_and_native_bindings(self):
        structures = self.env["hr.payroll.structure"].search([
            ("code", "in", list(self.EXPECTED_STRUCTURES)),
        ])
        self.assertEqual(set(structures.mapped("code")), self.EXPECTED_STRUCTURES)
        self.assertTrue(all(structures.mapped("active")))
        legacy = self.env["hr.payroll.structure"].search([("code", "in", ["CO_MENSUAL", "CO_QUINCENAL", "CO_SEMANAL"])])
        self.assertFalse(legacy.filtered("active"), "Las frecuencias antiguas no deben seguir siendo estructuras activas.")
        self.assertEqual(set(self.parameter.salary_rule_ids.mapped("code")), self.EXPECTED_RULES)
        self.assertEqual(len(self.parameter.salary_rule_ids.filtered(lambda rule: rule.validation_state == "valid")), len(self.EXPECTED_RULES))

        input_types = self.env["hr.payslip.input.type"].search([
            ("code", "in", list(self.EXPECTED_INPUTS)),
        ])
        self.assertEqual(set(input_types.mapped("code")), self.EXPECTED_INPUTS)
        for structure in structures:
            self.assertEqual(structure.type_id.default_struct_id, structure)
            native_rules = structure.rule_ids.filtered("co_payroll_rule_id")
            self.assertEqual(set(native_rules.mapped("co_payroll_rule_id.code")), self.EXPECTED_RULES)

    def test_all_rules_evaluate_in_low_and_high_ordinary_cases(self):
        old_withholding = self.parameter.withholding_enabled
        self.parameter.withholding_enabled = True
        try:
            sources = {code: (2.0 if code in {"HED", "HEN", "HDF", "RN"} else 100000.0) for code in self.EXPECTED_INPUTS}
            sources["RETENCION"] = 80000.0
            covered = set()
            for basic_wage in (3000000.0, 10000000.0):
                values = {
                    "basic_wage": basic_wage,
                    "gross_wage": basic_wage,
                    "deduction_total": 0.0,
                    "net_wage": basic_wage,
                    "employer_cost": 0.0,
                    "ibc_base": basic_wage,
                    "worked_days": 30.0,
                    "worked_hours": 210.0,
                    "employee_count": 1,
                    "salary_mode": "ordinary",
                    "risk_class": "I",
                }
                result = _evaluate_configured_rules(
                    self.parameter.salary_rule_ids,
                    values,
                    {"BASIC": basic_wage, **sources},
                    self.parameter,
                )["rule_results"]
                self.assertEqual(len(result), len(self.EXPECTED_RULES))
                for item in result:
                    if item["condition_met"]:
                        self.assertGreater(item["amount"], 0.0, item["code"])
                        covered.add(item["code"])
            self.assertEqual(covered, self.EXPECTED_RULES)
        finally:
            self.parameter.withholding_enabled = old_withholding

    def test_integral_ordinary_limits_risk_classes_and_direct_dian_mappings(self):
        self.assertEqual(self.parameter.normalize_ibc(30000000.0, 30, "integral"), 21000000.0)
        self.assertEqual(self.parameter.normalize_ibc(100000.0, 30, "ordinary"), self.parameter.minimum_wage)
        self.assertEqual(self.parameter.normalize_ibc(100000000.0, 30, "ordinary"), self.parameter.minimum_wage * 25)
        self.assertEqual(self.parameter.get_arl_rate("I"), 0.522)
        self.assertEqual(self.parameter.get_arl_rate("V"), 6.960)

        mapping_model = self.env["l10n.co.payroll.rule.mapping"]
        direct_codes = {
            "AUX_TRANSP", "HED", "HEN", "HDF", "RN", "COMISION", "BONO_SAL", "BONO_NOSAL",
            "SALUD_EMP", "PENSION_EMP", "FSP", "RETENCION", "EMBARGO", "PRESTAMO", "VAC_PAGADA",
            "INCAPACIDAD", "LIC_MAT", "LIC_PAT", "LIC_REM", "PRIMA_PAGO", "CESANTIA_PAGO",
            "INTERES_CESANT", "REINTEGRO",
        }
        mappings = mapping_model.search([
            ("parameter_id", "=", self.parameter.id),
            ("code", "in", list(direct_codes)),
        ])
        self.assertEqual(set(mappings.mapped("code")), direct_codes)
        self.assertTrue(all(mapping.salary_rule_id for mapping in mappings))
        self.assertTrue(all(mapping.dian_concept for mapping in mappings if "dian_concept" in mapping._fields))

    def test_period_type_catalog_is_complete(self):
        selection = dict(self.env["l10n.co.payroll.period"]._fields["period_type"].selection)
        self.assertEqual(set(selection), {"monthly", "biweekly", "weekly", "off_cycle"})
        self.assertTrue(self.env["l10n.co.payroll.pila.config"].search_count([
            ("company_id", "=", self.env.company.id),
            ("active", "=", True),
        ]))

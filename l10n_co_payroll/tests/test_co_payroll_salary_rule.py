from collections import defaultdict

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestCoPayrollSalaryRule(TransactionCase):
    def test_formula_engine_chains_rules_and_returns_auditable_values(self):
        parameter = self.env["l10n.co.payroll.parameter"].create({
            "company_id": self.env.company.id,
            "year": 2096,
            "minimum_wage": 1000,
            "effective_from": fields.Date.from_string("2096-01-01"),
            "effective_to": fields.Date.from_string("2096-12-31"),
        })
        first = self.env["l10n.co.payroll.salary.rule"].create({
            "company_id": self.env.company.id,
            "parameter_id": parameter.id,
            "sequence": 10,
            "name": "Auxilio de prueba",
            "code": "AUX_TEST",
            "concept_type": "earning",
            "amount_expression": "minimum_wage * 0.10",
        })
        second = self.env["l10n.co.payroll.salary.rule"].create({
            "company_id": self.env.company.id,
            "parameter_id": parameter.id,
            "sequence": 20,
            "name": "Descuento de prueba",
            "code": "DED_TEST",
            "concept_type": "deduction",
            "amount_expression": "rule('AUX_TEST') * 0.20",
        })
        first.action_validate_formula()
        second.action_validate_formula()
        values = self.env["l10n.co.payroll.period"]._summarize_payslips(self.env["hr.payslip"], parameter)
        self.assertEqual(values["gross_wage"], 100.0)
        self.assertEqual(values["deduction_total"], 20.0)
        self.assertEqual(values["net_wage"], 80.0)
        self.assertEqual(len(values["rule_results"]), 2)

    def test_formula_engine_rejects_unsafe_python(self):
        parameter = self.env["l10n.co.payroll.parameter"].create({"company_id": self.env.company.id, "year": 2095})
        with self.assertRaises(ValidationError):
            self.env["l10n.co.payroll.salary.rule"].create({
                "company_id": self.env.company.id,
                "parameter_id": parameter.id,
                "name": "Regla insegura",
                "code": "UNSAFE",
                "amount_expression": "__import__('os').system('whoami')",
            })

    def test_native_payroll_rule_bridge_evaluates_configured_rule(self):
        parameter = self.env["l10n.co.payroll.parameter"].create({
            "company_id": self.env.company.id,
            "year": 2097,
            "minimum_wage": 1300000,
            "effective_from": fields.Date.from_string("2097-01-01"),
            "effective_to": fields.Date.from_string("2097-12-31"),
        })
        configured = self.env["l10n.co.payroll.salary.rule"].create({
            "company_id": self.env.company.id,
            "parameter_id": parameter.id,
            "sequence": 10,
            "name": "Auxilio nativo de prueba",
            "code": "NATIVE_TEST",
            "concept_type": "earning",
            "amount_expression": "minimum_wage * 0.10",
        })
        structure = self.env.ref("hr_payroll.default_structure", raise_if_not_found=False)
        self.assertTrue(structure, "La estructura salarial estándar debe estar disponible")
        configured._ensure_native_rules(structure)
        native = self.env["hr.salary.rule"].search([("co_payroll_rule_id", "=", configured.id)], limit=1)
        self.assertTrue(native)

        employee = self.env["hr.employee"].create({
            "name": "Empleado prueba puente",
            "company_id": self.env.company.id,
        })
        payslip = self.env["hr.payslip"].new({
            "name": "Recibo puente",
            "employee_id": employee.id,
            "struct_id": structure.id,
            "date_from": fields.Date.from_string("2097-01-01"),
            "date_to": fields.Date.from_string("2097-01-31"),
            "company_id": self.env.company.id,
        })
        payslip.update({
            "co_formula_parameter_id": parameter.id,
            "co_formula_gross_wage": 0.0,
            "co_formula_deduction_total": 0.0,
            "co_formula_employer_cost": 0.0,
        })
        localdict = {
            "payslip": payslip,
            "employee": employee,
            "categories": defaultdict(float),
            "rules": defaultdict(float),
            "worked_days": defaultdict(float),
            "inputs": defaultdict(float),
            "result_rules": {},
            "_co_formula_results": {},
            "basic_wage": 0.0,
            "gross_wage": 0.0,
            "deduction_total": 0.0,
            "worked_days_total": 30.0,
            "minimum_wage": 1300000.0,
            "transport_allowance": 0.0,
            "parameter": parameter,
            "date_from": payslip.date_from,
            "date_to": payslip.date_to,
        }
        amount, qty, rate = native._compute_rule(localdict)
        self.assertEqual(amount, 130000.0)
        self.assertEqual(qty, 1.0)
        self.assertEqual(rate, 100.0)

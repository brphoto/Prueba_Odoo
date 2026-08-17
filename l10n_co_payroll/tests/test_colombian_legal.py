from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestColombianLegalControls(TransactionCase):
    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.employee = self.env["hr.employee"].create({"name": "Colaborador legal prueba", "company_id": self.company.id})

    def test_settlement_uses_statutory_360_day_formulas(self):
        parameter = self.env["l10n.co.payroll.parameter"].create({
            "company_id": self.company.id, "year": 2095,
            "minimum_wage": 1000000, "transport_allowance": 100000,
            "severance_days_per_year": 30, "bonus_days_per_year": 30,
            "vacation_days_per_year": 15, "severance_interest_rate": 12,
        })
        settlement = self.env["l10n.co.payroll.settlement"].create({
            "company_id": self.company.id, "employee_id": self.employee.id,
            "termination_date": "2095-12-31", "base_salary": 2000000,
            "transport_allowance": 249095, "service_days": 365,
            "parameter_id": parameter.id,
        })
        settlement.action_calculate()
        base = 2249095
        self.assertAlmostEqual(settlement.severance, base * 365 / 360, places=2)
        self.assertAlmostEqual(settlement.bonus, base * 365 / 360, places=2)
        self.assertAlmostEqual(settlement.severance_interest, base * 365 / 360 * .12 * 365 / 360, places=2)

    def test_incapacity_tranches_and_dian_deadline(self):
        period = self.env["l10n.co.payroll.period"].create({
            "company_id": self.company.id, "date_from": "2094-08-01", "date_to": "2094-08-31",
            "employee_ids": [(6, 0, self.employee.ids)],
        })
        novelty = self.env["l10n.co.payroll.novelty"].create({
            "period_id": period.id, "employee_id": self.employee.id, "novelty_type": "ige",
            "date_from": "2094-08-01", "date_to": "2094-08-05", "days": 5, "base_salary": 3000000,
        })
        self.assertEqual(novelty.responsible_entity, "eps")
        self.assertEqual(novelty.amount_calculated, 400000)
        if "dian_due_date" in period._fields:
            self.assertEqual(period.dian_due_date.isoformat(), "2094-09-10")

    def test_withholding_table_is_versioned_and_editable(self):
        parameter = self.env["l10n.co.payroll.parameter"].create({
            "company_id": self.company.id, "year": 2093, "uvt_value": 100,
            "withholding_enabled": True,
        })
        value = parameter.calculate_withholding(20000)
        self.assertEqual(value, 2400)
        self.assertEqual(len(parameter.withholding_bracket_ids), 7)

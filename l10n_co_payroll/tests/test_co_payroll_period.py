from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestCoPayrollPeriod(TransactionCase):
    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.employee = self.env["hr.employee"].create({"name": "Empleado prueba nómina", "company_id": self.company.id})

    def _create_period(self, date_from="2099-04-01", date_to="2099-04-30"):
        return self.env["l10n.co.payroll.period"].create({
            "company_id": self.company.id,
            "date_from": date_from,
            "date_to": date_to,
            "employee_ids": [(6, 0, self.employee.ids)],
        })

    def _create_payslip(self, date_from="2099-04-01", date_to="2099-04-30"):
        return self.env["hr.payslip"].create({
            "name": "REC-PRUEBA-001",
            "employee_id": self.employee.id,
            "company_id": self.company.id,
            "date_from": date_from,
            "date_to": date_to,
        })

    def test_prepare_and_close_requires_validated_payslip(self):
        payslip = self._create_payslip()
        period = self._create_period()
        period.action_prepare()
        self.assertEqual(period.state, "ready")
        self.assertEqual(len(period.line_ids), 1)
        self.assertGreaterEqual(period.blocking_issue_count, 1)
        with self.assertRaises(UserError):
            period.action_close()
        payslip.write({"state": "validated", "done_date": fields.Datetime.now()})
        period.action_prepare()
        period.action_close()
        self.assertEqual(period.state, "closed")
        self.assertTrue(period.closed_by)

    def test_csv_export_and_report_are_available(self):
        payslip = self._create_payslip("2099-05-01", "2099-05-31")
        payslip.write({"state": "validated", "done_date": fields.Datetime.now()})
        period = self._create_period("2099-05-01", "2099-05-31")
        period.action_prepare()
        csv_action = period.action_export_csv()
        self.assertEqual(csv_action["type"], "ir.actions.act_url")
        pila_action = period.action_export_pila_csv()
        self.assertEqual(pila_action["type"], "ir.actions.act_url")
        report = self.env.ref("l10n_co_payroll.action_report_co_payroll_period")
        pdf, file_type = report._render_qweb_pdf(report.report_name, period.ids)
        self.assertIn(file_type, ("pdf", "html"))
        self.assertTrue(pdf)

    def test_double_approval_and_novelty_configuration(self):
        self.env["l10n.co.payroll.parameter"].create({
            "company_id": self.company.id,
            "year": 2099,
            "approval_mode": "double",
            "require_novelty_approval": True,
        })
        payslip = self._create_payslip("2099-06-01", "2099-06-30")
        payslip.write({"state": "validated", "done_date": fields.Datetime.now()})
        period = self._create_period("2099-06-01", "2099-06-30")
        novelty = self.env["l10n.co.payroll.novelty"].create({
            "period_id": period.id,
            "employee_id": self.employee.id,
            "novelty_type": "vac",
            "date_from": "2099-06-10",
            "date_to": "2099-06-12",
            "days": 3,
        })
        period.action_prepare()
        self.assertEqual(period.approval_mode, "double")
        self.assertEqual(period.pending_novelty_count, 1)
        novelty.action_approve()
        period.action_prepare()
        period.action_approve()
        self.assertEqual(period.approval_state, "first_approved")
        manager_group = self.env.ref("l10n_co_payroll.group_co_payroll_manager")
        second_user = self.env["res.users"].create({
            "name": "Supervisor de prueba 2",
            "login": "supervisor-prueba-2-2099",
            "email": "supervisor-prueba-2-2099@example.com",
            "group_ids": [(6, 0, [manager_group.id])],
        })
        period.with_user(second_user).action_approve()
        self.assertEqual(period.approval_state, "approved")
        period.action_close()
        self.assertEqual(period.state, "closed")

    def test_duplicate_period_is_rejected(self):
        self._create_period("2099-07-01", "2099-07-31")
        with self.assertRaises(ValidationError):
            self._create_period("2099-07-01", "2099-07-31")

    def test_approval_and_warning_settings_are_inherited(self):
        self.env["l10n.co.payroll.parameter"].create({
            "company_id": self.company.id,
            "year": 2098,
            "approval_mode": "single",
            "block_on_warnings": True,
            "require_novelty_approval": False,
        })
        period = self._create_period("2098-08-01", "2098-08-31")
        self.assertEqual(period.approval_mode, "single")
        self.assertEqual(period.approval_state, "pending")
        self.assertTrue(period.block_on_warnings)
        self.assertFalse(period.require_novelty_approval)

    def test_operational_records_are_read_only_for_auditor(self):
        auditor_group = self.env.ref("l10n_co_payroll.group_co_payroll_auditor")
        auditor = self.env["res.users"].create({
            "name": "Auditor de prueba 2099",
            "login": "auditor-prueba-2099",
            "email": "auditor-prueba-2099@example.com",
            "group_ids": [(6, 0, [auditor_group.id])],
        })
        self.assertFalse(self.env["l10n.co.payroll.period"].with_user(auditor).has_access("write"))
        self.assertFalse(self.env["l10n.co.payroll.period.line"].with_user(auditor).has_access("create"))
        self.assertFalse(self.env["l10n.co.payroll.period.issue"].with_user(auditor).has_access("unlink"))

    def test_legal_parameter_versions_select_by_period_date(self):
        self.env["l10n.co.payroll.parameter"].create({
            "company_id": self.company.id,
            "year": 2097,
            "version": 1,
            "effective_from": "2097-01-01",
            "effective_to": "2097-06-30",
            "minimum_wage": 1000,
        })
        version_two = self.env["l10n.co.payroll.parameter"].create({
            "company_id": self.company.id,
            "year": 2097,
            "version": 2,
            "effective_from": "2097-07-01",
            "effective_to": "2097-12-31",
            "minimum_wage": 2000,
        })
        period = self._create_period("2097-08-01", "2097-08-31")
        self.assertEqual(period.parameter_id, version_two)
        self.assertEqual(period.parameter_id.minimum_wage, 2000)

    def test_colombian_ibc_cap_integral_salary_and_solidarity(self):
        parameter = self.env["l10n.co.payroll.parameter"].create({
            "company_id": self.company.id,
            "year": 2096,
            "minimum_wage": 1000,
            "maximum_ibc_multiple": 25,
            "integral_ibc_ratio": 70,
        })
        self.assertEqual(parameter.normalize_ibc(50000, 30), 25000)
        self.assertEqual(parameter.normalize_ibc(13000, 30, "integral"), 9100)
        self.assertEqual(parameter.get_solidarity_rate(4000), 1.0)
        self.assertEqual(parameter.get_solidarity_rate(16500), 1.2)

    def test_social_profile_pila_adjustment_and_settlement(self):
        self.employee.write({"identification_id": "999999999"})
        social = self.env["l10n.co.payroll.social"].create({
            "employee_id": self.employee.id,
            "effective_from": "2099-09-01",
            "contributor_type": "01",
            "contributor_subtype": "0",
            "eps_code": "EPS001",
            "pension_code": "AFP001",
            "arl_code": "ARL001",
            "ccf_code": "CCF001",
        })
        social.action_activate()
        adjustment = self.env["l10n.co.payroll.adjustment"].create({
            "company_id": self.company.id,
            "employee_id": self.employee.id,
            "adjustment_type": "retroactive",
            "amount": 150,
            "date": "2099-09-15",
        })
        adjustment.action_approve()
        adjustment.action_apply()
        payslip = self._create_payslip("2099-09-01", "2099-09-30")
        payslip.write({"state": "validated", "done_date": fields.Datetime.now()})
        period = self._create_period("2099-09-01", "2099-09-30")
        adjustment.period_id = period
        period.action_prepare()
        self.assertEqual(period.line_ids.social_profile_id, social)
        self.assertEqual(period.line_ids.adjustment_total, 150)
        config = self.env["l10n.co.payroll.pila.config"].create({"company_id": self.company.id, "name": "PILA prueba", "include_header": True})
        pila_file = self.env["l10n.co.payroll.pila.file"].create({"company_id": self.company.id, "period_id": period.id, "config_id": config.id})
        pila_file.action_generate()
        self.assertEqual(pila_file.state, "generated")
        self.assertTrue(pila_file.attachment_id)
        settlement = self.env["l10n.co.payroll.settlement"].create({
            "company_id": self.company.id,
            "employee_id": self.employee.id,
            "base_salary": 3000,
            "pending_wages": 100,
            "severance": 200,
            "deductions": 50,
        })
        settlement.action_calculate()
        self.assertEqual(settlement.total, 250)

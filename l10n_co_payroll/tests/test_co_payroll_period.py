import base64

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

    def test_period_consolidates_multiple_payrolls_for_one_employee(self):
        first = self._create_payslip("2099-10-01", "2099-10-15")
        second = self._create_payslip("2099-10-16", "2099-10-31")
        first.write({"name": "REC-PRUEBA-QUINCENA-1", "state": "validated", "done_date": fields.Datetime.now()})
        second.write({"name": "REC-PRUEBA-QUINCENA-2", "state": "validated", "done_date": fields.Datetime.now()})
        period = self._create_period("2099-10-01", "2099-10-31")

        period.action_prepare()

        self.assertEqual(len(period.line_ids), 1)
        self.assertEqual(period.line_ids.payslip_count, 2)
        self.assertEqual(set(period.line_ids.source_payslip_ids.ids), {first.id, second.id})

    def test_administrator_catalog_fills_pila_code(self):
        administrator = self.env["l10n.co.payroll.administrator"].create({
            "name": "EPS de prueba",
            "company_id": self.company.id,
            "kind": "eps",
            "code": "EPS-TEST",
        })
        social = self.env["l10n.co.payroll.social"].create({
            "employee_id": self.employee.id,
            "effective_from": "2099-11-01",
            "eps_id": administrator.id,
        })

        self.assertEqual(social.eps_code, "EPS-TEST")

    def test_administrator_accounting_lines_keep_third_party_traceability(self):
        partner = self.env["res.partner"].create({"name": "EPS contable prueba"})
        debit_account = self.env["account.account"].create({
            "name": "Gasto salud prueba",
            "code": "519901",
            "account_type": "expense",
            "company_ids": [(6, 0, [self.company.id])],
        })
        credit_account = self.env["account.account"].create({
            "name": "EPS por pagar prueba",
            "code": "237001",
            "account_type": "liability_current",
            "company_ids": [(6, 0, [self.company.id])],
        })
        administrator = self.env["l10n.co.payroll.administrator"].create({
            "name": "EPS contable",
            "company_id": self.company.id,
            "kind": "eps",
            "code": "EPS-CONT",
            "partner_id": partner.id,
            "debit_account_id": debit_account.id,
            "credit_account_id": credit_account.id,
        })
        social = self.env["l10n.co.payroll.social"].create({
            "employee_id": self.employee.id,
            "effective_from": "2099-08-01",
            "coverage_mode": "full",
            "eps_id": administrator.id,
        })
        period = self._create_period("2099-08-01", "2099-08-31")
        line = self.env["l10n.co.payroll.period.line"].create({
            "period_id": period.id,
            "employee_id": self.employee.id,
            "social_profile_id": social.id,
            "pila_reporting_mode": "full",
            "gross_wage": 1000,
            "deduction_total": 40,
            "net_wage": 960,
            "employer_cost": 120,
            "social_employee_total": 40,
            "health_employee": 40,
            "health_employer": 120,
        })
        accounts = {
            "expense": debit_account,
            "payable": credit_account,
            "deductions": credit_account,
            "employer": debit_account,
            "analytic": False,
            "journal": False,
        }

        values = period._administrator_accounting_lines(accounts)
        administrator_lines = [value for value in values if value.get("co_payroll_administrator_id")]

        self.assertEqual(line.social_profile_id, social)
        self.assertEqual(sum(value["debit"] for value in values), sum(value["credit"] for value in values))
        self.assertEqual(sum(value["credit"] for value in administrator_lines if value["co_payroll_component"] == "employee"), 40)
        self.assertEqual(sum(value["credit"] for value in administrator_lines if value["co_payroll_component"] == "employer"), 120)
        self.assertEqual(sum(value["debit"] for value in administrator_lines), 120)
        self.assertTrue(all(value["partner_id"] == partner.id for value in administrator_lines))
        self.assertTrue(all("EPS contable" in value["name"] for value in administrator_lines))

    def test_social_coverage_modes_keep_external_cases_traceable(self):
        manual = self.env["l10n.co.payroll.social"].create({
            "employee_id": self.employee.id,
            "effective_from": "2099-06-01",
            "coverage_mode": "manual",
            "manual_reference": "Operador externo 2029-06",
        })
        manual.action_activate()
        self.assertFalse(manual.is_pila_reportable)
        self.assertEqual(manual.get_missing_administrators(), [])

        payslip = self._create_payslip("2099-06-01", "2099-06-30")
        payslip.write({"state": "validated", "done_date": fields.Datetime.now()})
        period = self._create_period("2099-06-01", "2099-06-30")
        period.action_prepare()
        self.assertEqual(period.line_ids.pila_reporting_mode, "manual")
        self.assertEqual(period.line_ids.pila_manual_reference, "Operador externo 2029-06")
        self.assertGreater(period.diagnostic_count, 0)
        self.assertEqual(period.action_open_diagnostics()["res_model"], "l10n.co.payroll.period.diagnostic")

    def test_client_import_loads_reusable_catalogs(self):
        content = "tipo;codigo;nombre\neps;EPS-IMPORT;EPS importada\n"
        wizard = self.env["l10n.co.payroll.client.import.wizard"].create({
            "import_type": "administrator",
            "company_id": self.company.id,
            "import_file": base64.b64encode(content.encode("utf-8-sig")),
            "filename": "administradoras.csv",
        })
        wizard.action_import()
        self.assertEqual(wizard.state, "imported")
        self.assertTrue(self.env["l10n.co.payroll.administrator"].search([("code", "=", "EPS-IMPORT"), ("company_id", "=", self.company.id)]))

    def test_period_wizard_can_prepare_without_manual_open_step(self):
        payslip = self._create_payslip("2099-07-01", "2099-07-31")
        payslip.write({"state": "validated", "done_date": fields.Datetime.now()})
        wizard = self.env["l10n.co.payroll.period.wizard"].create({
            "company_id": self.company.id,
            "date_from": "2099-07-01",
            "date_to": "2099-07-31",
            "prepare_now": True,
        })
        action = wizard.action_create_period()
        period = self.env["l10n.co.payroll.period"].browse(action["res_id"])
        self.assertEqual(period.state, "ready")
        self.assertEqual(len(period.line_ids), 1)

    def test_closed_period_creates_linked_rectification(self):
        payslip = self._create_payslip("2099-12-01", "2099-12-31")
        payslip.write({"state": "validated", "done_date": fields.Datetime.now()})
        period = self._create_period("2099-12-01", "2099-12-31")
        period.action_prepare()
        period.action_close()

        rectification = period.action_create_rectification()
        rectified = self.env["l10n.co.payroll.period"].browse(rectification["res_id"])
        self.assertEqual(rectified.rectifies_period_id, period)
        self.assertTrue(rectified.is_rectification)

    def test_cost_center_priority_is_employee_then_department_then_company(self):
        company_center = self.env["l10n.co.payroll.cost.center"].create({"name": "General", "code": "GEN"})
        employee_center = self.env["l10n.co.payroll.cost.center"].create({"name": "Empleado", "code": "EMP"})
        company_center.default_for_company = True
        self.assertEqual(self.env["l10n.co.payroll.cost.center"].get_for_employee(self.employee), company_center)
        self.employee.co_payroll_cost_center_id = employee_center
        self.assertEqual(self.env["l10n.co.payroll.cost.center"].get_for_employee(self.employee), employee_center)

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

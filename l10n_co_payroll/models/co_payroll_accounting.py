from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CoPayrollAccountMoveLine(models.Model):
    _inherit = "account.move.line"

    co_payroll_administrator_id = fields.Many2one(
        "l10n.co.payroll.administrator",
        string="Administradora de nómina",
        readonly=True,
        copy=False,
        index=True,
    )
    co_payroll_period_line_id = fields.Many2one(
        "l10n.co.payroll.period.line",
        string="Línea consolidada de nómina",
        readonly=True,
        copy=False,
        index=True,
    )
    co_payroll_component = fields.Selection([
        ("employee", "Aporte empleado"),
        ("employer", "Aporte empleador"),
    ], string="Componente nómina", readonly=True, copy=False)


class CoPayrollPeriodAccounting(models.Model):
    _inherit = "l10n.co.payroll.period"

    accounting_state = fields.Selection([("pending", "Pendiente"), ("draft", "Borrador"), ("posted", "Contabilizado")], string="Contabilidad", default="pending", copy=False, tracking=True)
    account_journal_id = fields.Many2one("account.journal", string="Diario de nómina", domain="[('company_id', '=', company_id), ('type', '=', 'general')]")
    expense_account_id = fields.Many2one("account.account", string="Cuenta gasto nómina", domain="[('company_ids', 'in', [company_id])]" )
    payroll_payable_account_id = fields.Many2one("account.account", string="Cuenta por pagar nómina", domain="[('company_ids', 'in', [company_id])]" )
    deductions_account_id = fields.Many2one("account.account", string="Cuenta deducciones / terceros", domain="[('company_ids', 'in', [company_id])]" )
    employer_account_id = fields.Many2one("account.account", string="Cuenta aportes empresa", domain="[('company_ids', 'in', [company_id])]" )
    analytic_account_id = fields.Many2one("account.analytic.account", string="Cuenta analítica", domain="[('company_id', '=', company_id)]")
    account_move_id = fields.Many2one("account.move", string="Asiento de nómina", readonly=True, copy=False)
    provision_move_id = fields.Many2one("account.move", string="Asiento de provisiones", readonly=True, copy=False)
    accounting_debit = fields.Monetary(string="Débitos", compute="_compute_accounting_control", currency_field="currency_id")
    accounting_credit = fields.Monetary(string="Créditos", compute="_compute_accounting_control", currency_field="currency_id")
    accounting_difference = fields.Monetary(string="Diferencia contable", compute="_compute_accounting_control", currency_field="currency_id")
    accounting_balanced = fields.Boolean(string="Asiento cuadrado", compute="_compute_accounting_control")

    @api.depends("account_move_id.line_ids.debit", "account_move_id.line_ids.credit")
    def _compute_accounting_control(self):
        for period in self:
            period.accounting_debit = sum(period.account_move_id.line_ids.mapped("debit")) if period.account_move_id else 0.0
            period.accounting_credit = sum(period.account_move_id.line_ids.mapped("credit")) if period.account_move_id else 0.0
            period.accounting_difference = period.accounting_debit - period.accounting_credit
            period.accounting_balanced = bool(period.account_move_id) and abs(period.accounting_difference) <= 0.01

    def _get_accounting_accounts(self):
        self.ensure_one()
        parameter = self.parameter_id
        return {
            "journal": self.account_journal_id or (parameter.account_journal_id if parameter and "account_journal_id" in parameter._fields else False),
            "expense": self.expense_account_id or (parameter.expense_account_id if parameter and "expense_account_id" in parameter._fields else False),
            "payable": self.payroll_payable_account_id or (parameter.payroll_payable_account_id if parameter and "payroll_payable_account_id" in parameter._fields else False),
            "deductions": self.deductions_account_id or (parameter.deductions_account_id if parameter and "deductions_account_id" in parameter._fields else False),
            "employer": self.employer_account_id or (parameter.employer_account_id if parameter and "employer_account_id" in parameter._fields else False),
            "analytic": self.analytic_account_id or (parameter.analytic_account_id if parameter and "analytic_account_id" in parameter._fields else False),
        }

    def _ensure_not_sandbox(self):
        if any(period.is_sandbox for period in self):
            raise UserError(_("Los periodos sandbox no pueden generar asientos contables."))

    def _administrator_accounting_lines(self, accounts):
        """Build detailed third-party lines when the PILA catalog is configured.

        The summarized accounting remains the fallback. This method only uses
        administrators with an explicit debit/credit account, so adopting the
        catalog never makes an existing company configuration fail silently.
        """
        self.ensure_one()
        contributions = {}
        social_employee_total = sum(self.line_ids.mapped("social_employee_total"))
        fallback_employee = social_employee_total
        fallback_employer_debit = self.employer_total
        fallback_employer_credit = self.employer_total

        for period_line in self.line_ids:
            social = period_line.social_profile_id
            if not social:
                continue
            components = (
                (social.eps_id, _("Salud"), period_line.health_employee, period_line.health_employer),
                (social.pension_id, _("Pensión y solidaridad"), period_line.pension_employee + period_line.solidarity_employee, period_line.pension_employer),
                (social.arl_id, _("ARL"), 0.0, period_line.arl_employer),
                (social.ccf_id, _("Caja de compensación"), 0.0, period_line.ccf_employer),
            )
            for administrator, label, employee_amount, employer_amount in components:
                employee_amount = employee_amount or 0.0
                employer_amount = employer_amount or 0.0
                if not administrator:
                    continue
                assignment = self.env["l10n.co.payroll.administrator.assignment"].get_for(
                    self.company_id, period_line.employee_id, administrator.kind, administrator
                )
                resolved = assignment.administrator_id if assignment else administrator
                debit_account = (assignment.debit_account_id if assignment and assignment.debit_account_id else resolved.debit_account_id)
                credit_account = (assignment.credit_account_id if assignment and assignment.credit_account_id else resolved.credit_account_id)
                partner = (assignment.partner_id if assignment and assignment.partner_id else resolved.partner_id)
                analytic_account = (assignment.analytic_account_id if assignment and assignment.analytic_account_id else period_line.cost_center_id.analytic_account_id if period_line.cost_center_id else accounts["analytic"])
                # Keep account/third-party overrides in the grouping key. Two
                # employee or department assignments may point to the same
                # administrator but to different accounting destinations.
                key = (
                    resolved.id,
                    debit_account.id if debit_account else False,
                    credit_account.id if credit_account else False,
                    partner.id if partner else False,
                    analytic_account.id if analytic_account else False,
                )
                bucket = contributions.setdefault(key, {
                    "administrator": resolved,
                    "label": label,
                    "employee": 0.0,
                    "employer": 0.0,
                    "debit_account": debit_account,
                    "credit_account": credit_account,
                    "partner": partner,
                    "analytic": analytic_account,
                })
                if credit_account:
                    bucket["employee"] += employee_amount
                    bucket["employer"] += employer_amount
                    fallback_employee -= employee_amount
                    fallback_employer_credit -= employer_amount
                if debit_account:
                    bucket["debit_employer"] = bucket.get("debit_employer", 0.0) + employer_amount
                    fallback_employer_debit -= employer_amount

        line_vals = []
        analytic = {str(accounts["analytic"].id): 100} if accounts["analytic"] else False

        def add_line(account, debit, credit, label, partner=False, analytic_override=False, administrator=False, component=False, period_line=False):
            if account and (debit or credit):
                line_vals.append({
                    "name": "%s - %s" % (self.name, label),
                    "account_id": account.id,
                    "partner_id": partner.id if partner else False,
                    "debit": max(debit, 0.0),
                    "credit": max(credit, 0.0),
                    "analytic_distribution": ({str(analytic_override.id): 100} if analytic_override else analytic),
                    "co_payroll_administrator_id": administrator.id if administrator else False,
                    "co_payroll_period_line_id": period_line.id if period_line else False,
                    "co_payroll_component": component or False,
                })

        add_line(accounts["expense"], self.gross_total, 0.0, _("Devengado de nómina"))
        add_line(accounts["payable"], 0.0, self.payable_net_total or self.net_total, _("Neto por pagar"))
        add_line(accounts["deductions"], 0.0, max(self.deduction_total - social_employee_total, 0.0) + max(fallback_employee, 0.0) + self.additional_deduction_total, _("Deducciones y aportes empleado"))
        add_line(accounts["employer"], max(fallback_employer_debit, 0.0), max(fallback_employer_credit, 0.0), _("Aportes empresa no distribuidos"))

        for values in contributions.values():
            administrator_label = "%s (%s)" % (values["administrator"].display_name, values["administrator"].code)
            label = "%s - %s" % (administrator_label, values["label"])
            add_line(
                values["debit_account"], values.get("debit_employer", 0.0), 0.0,
                "%s - %s" % (label, _("empleador")), values["partner"], values["analytic"],
                values["administrator"], "employer",
            )
            add_line(
                values["credit_account"], 0.0, values["employee"],
                "%s - %s" % (label, _("empleado")), values["partner"], values["analytic"],
                values["administrator"], "employee",
            )
            add_line(
                values["credit_account"], 0.0, values["employer"],
                "%s - %s" % (label, _("empleador")), values["partner"], values["analytic"],
                values["administrator"], "employer",
            )
        return line_vals

    def action_create_accounting_move(self):
        self._ensure_not_sandbox()
        for period in self:
            if period.state not in ("ready", "closed"):
                raise UserError(_("Prepara o cierra el periodo antes de contabilizarlo."))
            if period.account_move_id:
                raise UserError(_("Este periodo ya tiene un asiento de nómina."))
            accounts = period._get_accounting_accounts()
            missing = [label for label, key in ((_("diario"), "journal"), (_("gasto"), "expense"), (_("por pagar"), "payable"), (_("deducciones"), "deductions"), (_("aportes empresa"), "employer")) if not accounts[key]]
            if missing:
                raise UserError(_("Configura las cuentas de %s antes de contabilizar.") % ", ".join(missing))
            administrator_configured = self.env["l10n.co.payroll.administrator"].search_count([
                ("company_id", "=", period.company_id.id),
                ("active", "=", True),
                "|", ("debit_account_id", "!=", False), ("credit_account_id", "!=", False),
            ])
            administrator_configured = administrator_configured or self.env["l10n.co.payroll.administrator.assignment"].search_count([
                ("company_id", "=", period.company_id.id), ("active", "=", True),
                "|", ("debit_account_id", "!=", False), ("credit_account_id", "!=", False),
            ])
            if administrator_configured:
                line_vals = [(0, 0, values) for values in period._administrator_accounting_lines(accounts)]
            else:
                line_vals = []
                analytic = {str(accounts["analytic"].id): 100} if accounts["analytic"] else False
                for account, debit, credit, label in [
                    (accounts["expense"], period.gross_total, 0.0, _("Devengado de nómina")),
                    (accounts["employer"], period.employer_total, 0.0, _("Aportes empresa")),
                    (accounts["payable"], 0.0, period.payable_net_total or period.net_total, _("Neto por pagar")),
                    (accounts["deductions"], 0.0, period.deduction_total + period.additional_deduction_total, _("Deducciones y terceros")),
                ]:
                    if debit or credit:
                        line_vals.append((0, 0, {"name": "%s - %s" % (period.name, label), "account_id": account.id, "debit": debit, "credit": credit, "analytic_distribution": analytic}))
                if period.employer_total and accounts["employer"]:
                    line_vals.append((0, 0, {"name": "%s - %s" % (period.name, _("Contrapartida aportes empresa")), "account_id": accounts["employer"].id, "debit": 0.0, "credit": period.employer_total, "analytic_distribution": analytic}))
            move = self.env["account.move"].create({"move_type": "entry", "date": period.payment_date or period.date_to, "journal_id": accounts["journal"].id, "ref": period.name, "line_ids": line_vals})
            if abs(sum(move.line_ids.mapped("debit")) - sum(move.line_ids.mapped("credit"))) > 0.01:
                move.unlink()
                raise UserError(_("El asiento generado no cuadra. Revisa los totales y cuentas antes de continuar."))
            period.write({"account_move_id": move.id, "accounting_state": "draft"})
            self.env["l10n.co.payroll.audit"].sudo().create({"company_id": period.company_id.id, "period_id": period.id, "res_model": period._name, "res_id": period.id, "action": "accounting", "description": _("Asiento de nómina creado en borrador: %s.") % move.display_name})
        return True

    def action_post_accounting_move(self):
        self._ensure_not_sandbox()
        if not (self.env.su or self.env.user._is_admin() or self.env.user.has_group("l10n_co_payroll.group_co_payroll_manager")):
            raise UserError(_("Solo un supervisor puede contabilizar la nómina."))
        for period in self:
            if not period.account_move_id:
                period.action_create_accounting_move()
            if period.account_move_id.state != "posted":
                period.account_move_id.action_post()
            period.write({"accounting_state": "posted"})
        return True

    def action_create_provision_move(self):
        self._ensure_not_sandbox()
        for period in self:
            if period.state not in ("ready", "closed"):
                raise UserError(_("Prepara o cierra el periodo antes de crear provisiones."))
            if period.provision_move_id:
                raise UserError(_("Este periodo ya tiene un asiento de provisiones."))
            accounts = period._get_accounting_accounts()
            if not accounts["journal"] or not accounts["expense"] or not accounts["employer"]:
                raise UserError(_("Configura diario, gasto y aportes empresa para provisiones."))
            provision_total = period.provision_severance + period.provision_severance_interest + period.provision_vacation + period.provision_bonus
            move = self.env["account.move"].create({"move_type": "entry", "date": period.date_to, "journal_id": accounts["journal"].id, "ref": "%s - Provisiones" % period.name, "line_ids": [(0, 0, {"name": _("Provisiones laborales - %s") % period.name, "account_id": accounts["expense"].id, "debit": provision_total, "credit": 0.0}), (0, 0, {"name": _("Provisiones laborales - %s") % period.name, "account_id": accounts["employer"].id, "debit": 0.0, "credit": provision_total})]})
            period.write({"provision_move_id": move.id})
        return True

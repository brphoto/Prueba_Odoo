from odoo import _, api, fields, models
from odoo.exceptions import UserError


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

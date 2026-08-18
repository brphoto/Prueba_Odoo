import base64
import csv
import io

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CoPayrollPaymentBatch(models.Model):
    _name = "l10n.co.payroll.payment.batch"
    _description = "Lote de pagos de nómina"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "payment_date desc, id desc"
    _check_company_auto = True

    name = fields.Char(string="Referencia", required=True, copy=False, default=lambda self: _("Pago de nómina"), tracking=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    period_id = fields.Many2one("l10n.co.payroll.period", required=True, ondelete="restrict", index=True)
    payment_date = fields.Date(string="Fecha de pago", required=True, default=fields.Date.context_today)
    journal_id = fields.Many2one("account.journal", string="Diario bancario", domain="[('company_id', '=', company_id), ('type', 'in', ['bank', 'cash'])]")
    bank_format_id = fields.Many2one("l10n.co.payroll.bank.format", string="Formato bancario", domain="[('company_id', '=', company_id), ('active', '=', True)]", default=lambda self: self.env["l10n.co.payroll.bank.format"].get_default(self.env.company))
    state = fields.Selection([("draft", "Borrador"), ("ready", "Listo"), ("exported", "Exportado"), ("paid", "Pagado"), ("cancelled", "Cancelado")], default="draft", required=True, tracking=True)
    line_ids = fields.One2many("l10n.co.payroll.payment.line", "batch_id", string="Beneficiarios", copy=False)
    total_amount = fields.Monetary(string="Total", compute="_compute_total", currency_field="currency_id")
    payment_count = fields.Integer(string="Número de beneficiarios", compute="_compute_total")
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)
    attachment_id = fields.Many2one("ir.attachment", string="Archivo bancario", readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        Format = self.env["l10n.co.payroll.bank.format"]
        for vals in vals_list:
            if not vals.get("bank_format_id"):
                company = self.env["res.company"].browse(vals.get("company_id") or self.env.company.id)
                default_format = Format.get_default(company)
                if default_format:
                    vals["bank_format_id"] = default_format.id
        return super().create(vals_list)

    def _compute_total(self):
        for record in self:
            record.total_amount = sum(record.line_ids.mapped("amount"))
            record.payment_count = len(record.line_ids)

    def action_prepare(self):
        for batch in self:
            if batch.period_id.is_sandbox:
                raise UserError(_("No se pueden preparar pagos desde un periodo sandbox."))
            if batch.period_id.state not in ("ready", "closed"):
                raise UserError(_("El periodo debe estar preparado o cerrado para preparar pagos."))
            batch.line_ids.sudo().unlink()
            values = []
            for period_line in batch.period_id.line_ids.filtered(lambda line: line.net_after_deductions > 0):
                allocations = self.env["l10n.co.payroll.payment.allocation"].search([
                    ("employee_id", "=", period_line.employee_id.id),
                    ("company_id", "=", batch.company_id.id),
                    ("active", "=", True),
                ], order="sequence, id")
                if allocations:
                    if abs(sum(allocations.mapped("percentage")) - 100.0) > 0.01:
                        values.append({"batch_id": batch.id, "period_line_id": period_line.id, "employee_id": period_line.employee_id.id, "amount": period_line.net_after_deductions, "state": "error", "error_message": _("La distribución bancaria debe sumar 100%%.")})
                        continue
                    for allocation in allocations:
                        values.append({"batch_id": batch.id, "period_line_id": period_line.id, "employee_id": period_line.employee_id.id, "bank_account_id": allocation.bank_account_id.id, "allocation_id": allocation.id, "amount": period_line.net_after_deductions * allocation.percentage / 100.0, "state": "pending", "error_message": False})
                    continue
                bank = period_line.employee_id.bank_account_ids.filtered(lambda account: account.allow_out_payment)[:1] or period_line.employee_id.bank_account_ids[:1]
                values.append({"batch_id": batch.id, "period_line_id": period_line.id, "employee_id": period_line.employee_id.id, "bank_account_id": bank.id if bank else False, "amount": period_line.net_after_deductions, "state": "pending" if bank else "error", "error_message": False if bank else _("No hay cuenta bancaria configurada.")})
            self.env["l10n.co.payroll.payment.line"].sudo().create(values)
            errors = batch.line_ids.filtered(lambda line: line.state == "error")
            if errors:
                raise UserError(_("Hay %s beneficiarios sin cuenta bancaria.") % len(errors))
            batch.write({"state": "ready"})
        return True

    def action_export_csv(self):
        for batch in self:
            if batch.state not in ("ready", "exported"):
                raise UserError(_("Prepara el lote antes de exportar pagos."))
            bank_format = batch.bank_format_id or self.env["l10n.co.payroll.bank.format"].get_default(batch.company_id)
            delimiter = bank_format.delimiter if bank_format else ";"
            line_terminator = "\r\n" if not bank_format or bank_format.line_ending == "crlf" else "\n"
            output = io.StringIO(newline="")
            writer = csv.writer(output, delimiter=delimiter, lineterminator=line_terminator)
            if not bank_format or bank_format.include_header:
                writer.writerow(["Identificación", "Beneficiario", "Cuenta", "Banco", "Valor"])
            for line in batch.line_ids:
                writer.writerow([line.employee_id.identification_id or "", line.employee_id.name, line.bank_account_id.acc_number or "", line.bank_account_id.bank_id.name if line.bank_account_id.bank_id else "", line.amount])
            encoding = bank_format.encoding if bank_format else "utf-8-sig"
            data = output.getvalue().encode(encoding, errors="replace")
            prefix = bank_format.filename_prefix if bank_format else "PAGOS_NOMINA"
            attachment = self.env["ir.attachment"].create({"name": "%s_%s.csv" % (prefix, batch.name), "type": "binary", "datas": base64.b64encode(data), "res_model": batch._name, "res_id": batch.id, "mimetype": "text/csv"})
            batch.write({"attachment_id": attachment.id, "state": "exported"})
            self.env["l10n.co.payroll.audit"].sudo().create({"company_id": batch.company_id.id, "period_id": batch.period_id.id, "res_model": batch._name, "res_id": batch.id, "action": "payment", "description": _("Archivo bancario generado.")})
            return {"type": "ir.actions.act_url", "url": "/web/content/%s?download=true" % attachment.id, "target": "self"}
        return True

    def action_mark_paid(self):
        self.filtered(lambda batch: batch.state in ("ready", "exported")).write({"state": "paid"})
        return True


class CoPayrollPaymentLine(models.Model):
    _name = "l10n.co.payroll.payment.line"
    _description = "Beneficiario de pago de nómina"
    _order = "employee_id"
    _check_company_auto = True

    batch_id = fields.Many2one("l10n.co.payroll.payment.batch", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="batch_id.company_id", store=True, readonly=True)
    period_line_id = fields.Many2one("l10n.co.payroll.period.line", required=True, readonly=True)
    employee_id = fields.Many2one("hr.employee", required=True, readonly=True)
    bank_account_id = fields.Many2one("res.partner.bank", readonly=True)
    allocation_id = fields.Many2one("l10n.co.payroll.payment.allocation", string="Distribución", readonly=True)
    amount = fields.Monetary(required=True, currency_field="currency_id", readonly=True)
    state = fields.Selection([("pending", "Pendiente"), ("error", "Error"), ("paid", "Pagado")], default="pending", required=True, readonly=True)
    error_message = fields.Char(readonly=True)
    currency_id = fields.Many2one(related="batch_id.currency_id", readonly=True)

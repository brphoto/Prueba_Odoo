from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class CoPayrollPortalRequest(models.Model):
    _name = "l10n.co.payroll.portal.request"
    _description = "Solicitud del portal de empleados"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc"
    _check_company_auto = True

    name = fields.Char(required=True, default=lambda self: _("Solicitud de empleado"), tracking=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    employee_id = fields.Many2one("hr.employee", required=True, index=True)
    request_type = fields.Selection([("vacation", "Vacaciones"), ("permission", "Permiso"), ("data_change", "Cambio de datos"), ("bank_change", "Cambio de cuenta bancaria"), ("certificate", "Certificado"), ("other", "Otra")], required=True, default="other")
    leave_type_id = fields.Many2one("hr.leave.type", string="Tipo de ausencia", domain="[('company_id', '=', company_id)]")
    bank_account_number = fields.Char(string="Nueva cuenta bancaria", copy=False)
    bank_name = fields.Char(string="Banco", copy=False)
    masked_bank_account = fields.Char(string="Cuenta bancaria", compute="_compute_masked_bank_account")
    applied_record = fields.Reference(selection=[("hr.leave", "Ausencia"), ("res.partner.bank", "Cuenta bancaria")], string="Registro aplicado", readonly=True, copy=False)
    date_from = fields.Date()
    date_to = fields.Date()
    description = fields.Text(required=True)
    state = fields.Selection([("draft", "Borrador"), ("submitted", "Enviada"), ("approved", "Aprobada"), ("rejected", "Rechazada"), ("cancelled", "Cancelada")], default="draft", required=True, tracking=True)
    requested_by = fields.Many2one("res.users", required=True, default=lambda self: self.env.user, readonly=True)
    reviewed_by = fields.Many2one("res.users", readonly=True)
    reviewed_at = fields.Datetime(readonly=True)
    review_notes = fields.Text()

    @api.depends("bank_account_number")
    def _compute_masked_bank_account(self):
        for record in self:
            account = (record.bank_account_number or "").replace(" ", "")
            record.masked_bank_account = ("*" * max(len(account) - 4, 0) + account[-4:]) if account else False

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for record in self:
            if record.date_from and record.date_to and record.date_from > record.date_to:
                raise ValidationError(_("La fecha inicial no puede superar la final."))

    @api.constrains("request_type", "bank_account_number", "description")
    def _check_request_data(self):
        for record in self:
            if not (record.description or "").strip():
                raise ValidationError(_("La descripción de la solicitud es obligatoria."))
            if record.request_type == "bank_change":
                account = "".join((record.bank_account_number or "").split())
                if not account.isdigit() or len(account) < 4:
                    raise ValidationError(_("La cuenta bancaria debe contener únicamente números y al menos cuatro dígitos."))

    def action_submit(self):
        self.write({"state": "submitted"})

    def action_approve(self):
        if not (self.env.su or self.env.user._is_admin() or self.env.user.has_group("l10n_co_payroll.group_co_payroll_manager")):
            raise UserError(_("Solo un responsable de nómina puede aprobar solicitudes."))
        for record in self:
            if record.state != "submitted":
                raise UserError(_("Solo se pueden aprobar solicitudes enviadas."))
            vals = {"state": "approved", "reviewed_by": self.env.user.id, "reviewed_at": fields.Datetime.now()}
            if record.request_type == "vacation" and "hr.leave" in self.env.registry.models and record.date_from and record.date_to:
                leave_type = record.leave_type_id or self.env["hr.leave.type"].search([("company_id", "in", [False, record.company_id.id]), "|", ("name", "ilike", "vacaciones"), ("code", "ilike", "VAC")], limit=1)
                if leave_type:
                    leave = self.env["hr.leave"].sudo().create({"name": record.description, "employee_id": record.employee_id.id, "holiday_status_id": leave_type.id, "request_date_from": record.date_from, "request_date_to": record.date_to})
                    vals["applied_record"] = "hr.leave,%s" % leave.id
            elif record.request_type == "bank_change" and record.bank_account_number and "res.partner.bank" in self.env.registry.models:
                if not record.employee_id.address_home_id:
                    raise UserError(_("El empleado debe tener una dirección privada antes de aplicar el cambio bancario."))
                bank = self.env["res.bank"].sudo().search([("name", "ilike", record.bank_name)], limit=1) if record.bank_name else self.env["res.bank"]
                account = self.env["res.partner.bank"].sudo().create({"acc_number": "".join(record.bank_account_number.split()), "bank_id": bank.id if bank else False, "partner_id": record.employee_id.address_home_id.id, "allow_out_payment": True})
                if "bank_account_ids" in record.employee_id._fields:
                    record.employee_id.sudo().write({"bank_account_ids": [(4, account.id)]})
                vals["applied_record"] = "res.partner.bank,%s" % account.id
            record.write(vals)

    def action_reject(self):
        if not (self.env.su or self.env.user._is_admin() or self.env.user.has_group("l10n_co_payroll.group_co_payroll_manager")):
            raise UserError(_("Solo un responsable de nómina puede rechazar solicitudes."))
        for record in self:
            if record.state != "submitted":
                raise UserError(_("Solo se pueden rechazar solicitudes enviadas."))
        self.write({"state": "rejected", "reviewed_by": self.env.user.id, "reviewed_at": fields.Datetime.now()})

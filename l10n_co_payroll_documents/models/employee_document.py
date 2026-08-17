from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class CoPayrollEmployeeDocument(models.Model):
    _name = "l10n.co.payroll.employee.document"
    _description = "Documento laboral del empleado"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "document_date desc, id desc"
    _check_company_auto = True

    name = fields.Char(required=True, tracking=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    employee_id = fields.Many2one("hr.employee", required=True, index=True)
    document_type = fields.Selection([("certificate", "Certificado laboral"), ("income", "Certificado de ingresos"), ("payslip", "Desprendible"), ("contract", "Contrato"), ("social", "Seguridad social"), ("other", "Otro")], required=True, default="other")
    document_date = fields.Date(required=True, default=fields.Date.context_today)
    expiry_date = fields.Date()
    portal_visible = fields.Boolean(string="Visible en portal", default=False)
    attachment_id = fields.Many2one("ir.attachment", string="Archivo", ondelete="restrict")
    datas = fields.Binary(related="attachment_id.datas", readonly=False)
    filename = fields.Char(string="Nombre del archivo", related="attachment_id.name", readonly=False)
    state = fields.Selection([("draft", "Borrador"), ("published", "Publicado"), ("archived", "Archivado")], default="draft", required=True, tracking=True)
    notes = fields.Text()

    @api.constrains("document_date", "expiry_date")
    def _check_dates(self):
        for record in self:
            if record.expiry_date and record.expiry_date < record.document_date:
                raise ValidationError(_("La fecha de vencimiento no puede ser anterior al documento."))

    def action_publish(self):
        for record in self:
            if not record.attachment_id and not record.datas:
                raise UserError(_("Adjunta el documento antes de publicarlo."))
            record.write({"state": "published"})

    def action_archive(self):
        self.write({"state": "archived", "portal_visible": False})

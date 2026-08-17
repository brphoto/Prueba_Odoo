from odoo import fields, models


class CoPayrollPortalAccessLog(models.Model):
    _name = "l10n.co.payroll.portal.access.log"
    _description = "Acceso a información salarial del colaborador"
    _order = "accessed_at desc"
    _check_company_auto = True

    company_id = fields.Many2one("res.company", required=True, index=True)
    employee_id = fields.Many2one("hr.employee", string="Colaborador", required=True, index=True)
    payslip_id = fields.Many2one("hr.payslip", ondelete="set null")
    action = fields.Selection([("view", "Consulta"), ("download", "Descarga")], required=True)
    accessed_at = fields.Datetime(required=True, default=fields.Datetime.now, index=True)
    user_id = fields.Many2one("res.users", required=True, default=lambda self: self.env.user)
    ip_address = fields.Char()

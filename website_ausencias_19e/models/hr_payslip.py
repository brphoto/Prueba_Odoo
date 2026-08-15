from datetime import datetime, time
from datetime import datetime
from typing import DefaultDict
from datetime import datetime as dt
from unicodedata import name
from odoo import _, api, exceptions, fields, models
from odoo.exceptions import UserError,ValidationError


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'
        
    def print(self):
        payslip=self.env['hr.payslip'].sudo().search([('id','=',self.id)])
        try:
            return self.env['ir.actions.report'].sudo()._render_qweb_pdf("hr_payroll.action_report_payslip", [payslip.id])

        except :

            return "/hr_payslip"
        
class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    method_calc=fields.Selection([
        ('1', 'Metodo Normal'),
        ('2', 'Por Fecha de Contrato'),
        ('3','Caso Especial')], string='Metodo de cálculo')
    days_initial=fields.Integer(string='Dias Iniciales')
    date_initial=fields.Date(string='Fecha Inicial')
    partner_id = fields.Many2one('res.partner', string='Partner', ondelete='cascade', help="Partner-related data of the employee")
    address_home_id=fields.Many2one('res.partner',related='partner_id')
    def _create_portal_user(self):
        """ Create a portal user for the employee """
        for employee in self:
            partner=self.env['res.partner']
            empleado=partner.search([('email','=',employee.work_email)])
            if not empleado:
                partner = self.env['res.partner'].sudo().create({'name': employee.name, 'email': employee.work_email})
                employee.partner_id = partner.id
        return True    
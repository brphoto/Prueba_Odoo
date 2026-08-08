# -*- coding: utf-8 -*-
import base64
from io import BytesIO

import xlsxwriter

from odoo import fields, models


class RfmDashboardReportWizard(models.TransientModel):
    _name = 'crm.rfm.dashboard.report.wizard'
    _description = 'Asistente de reporte gerencial RFM'

    period = fields.Selection([
        ('30', 'Últimos 30 días'), ('90', 'Últimos 90 días'),
        ('365', 'Últimos 12 meses'), ('all', 'Todo el historial'),
    ], string='Período', default='90', required=True)
    category = fields.Selection([
        ('all', 'Todas'), ('a', 'A - Alto valor'),
        ('b', 'B - Valor medio'), ('c', 'C - Bajo valor'),
    ], string='Categoría RFM', default='all', required=True)
    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True,
        default=lambda self: self.env.company)

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref(
            'crm_customer_intelligence.action_report_rfm_dashboard').report_action(self)

    def action_export_xlsx(self):
        self.ensure_one()
        data = self.get_report_data()
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        title = workbook.add_format({'bold': True, 'font_size': 16, 'font_color': '#714B67'})
        header = workbook.add_format({'bold': True, 'bg_color': '#714B67', 'font_color': 'white'})
        number = workbook.add_format({'num_format': '#,##0.00'})
        sheet = workbook.add_worksheet('Resumen')
        sheet.write('A1', 'Reporte gerencial RFM', title)
        sheet.write_row('A3', ['Indicador', 'Resultado'], header)
        summary = [
            ('Clientes analizados', data.get('customer_count', 0)),
            ('Ventas del período', data.get('total_sales', 0)),
            ('Ticket promedio', data.get('average_ticket', 0)),
            ('Score RFM promedio', data.get('average_score', 0)),
            ('Clientes en riesgo', data.get('at_risk_count', 0)),
        ]
        for row, (label, value) in enumerate(summary, 3):
            sheet.write(row, 0, label); sheet.write(row, 1, value, number)
        sheet.set_column('A:A', 32); sheet.set_column('B:B', 20)
        segment = workbook.add_worksheet('Distribución RFM')
        segment.write_row('A1', ['Segmento', 'Clientes', 'Ventas'], header)
        for row, item in enumerate(data.get('distribution', []), 1):
            segment.write_row(row, 0, [item['label'], item['count'], item['sales']])
        segment.set_column('A:A', 24); segment.set_column('B:C', 16)
        customers = workbook.add_worksheet('Clientes principales')
        customers.write_row('A1', ['Cliente', 'Segmento', 'Total', 'Facturas'], header)
        for row, item in enumerate(data.get('top_customers', []), 1):
            customers.write_row(row, 0, [item['name'], item['category'], item['total'], item['invoice_count']])
        customers.set_column('A:A', 32); customers.set_column('B:D', 16)
        workbook.close()
        attachment = self.env['ir.attachment'].create({
            'name': 'reporte_rfm.xlsx', 'type': 'binary',
            'datas': base64.b64encode(output.getvalue()),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'res_model': self._name, 'res_id': self.id,
        })
        return {'type': 'ir.actions.act_url', 'url': f'/web/content/{attachment.id}?download=true', 'target': 'self'}

    def get_report_data(self):
        self.ensure_one()
        return self.env['res.partner'].get_rfm_dashboard_data(
            self.period, self.category)


class ReportRfmDashboard(models.AbstractModel):
    _name = 'report.crm_customer_intelligence.rfm_dashboard_report'
    _description = 'Reporte PDF del dashboard RFM'

    def _get_report_values(self, docids, data=None):
        docs = self.env['crm.rfm.dashboard.report.wizard'].browse(docids)
        wizard = docs[:1]
        return {
            'doc_ids': docids,
            'doc_model': 'crm.rfm.dashboard.report.wizard',
            'docs': docs,
            'wizard': wizard,
            'dashboard': wizard.get_report_data() if wizard else {},
            'company': wizard.company_id if wizard else self.env.company,
            'generated_at': fields.Datetime.now(),
        }

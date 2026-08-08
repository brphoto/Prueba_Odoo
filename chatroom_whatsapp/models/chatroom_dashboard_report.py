# -*- coding: utf-8 -*-
import base64
from io import BytesIO

import xlsxwriter

from odoo import _, fields, models


class ChatroomDashboardReportWizard(models.TransientModel):
    _name = 'chatroom.dashboard.report.wizard'
    _description = 'Asistente de reporte gerencial de Chatroom'

    period_days = fields.Selection([
        ('7', 'Últimos 7 días'),
        ('30', 'Últimos 30 días'),
        ('90', 'Últimos 90 días'),
        ('365', 'Últimos 12 meses'),
        ('0', 'Todo el historial'),
    ], string='Período', default='30', required=True)
    include_details = fields.Boolean(
        string='Incluir detalle por agente y etapa', default=True)
    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True,
        default=lambda self: self.env.company)

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref(
            'chatroom_whatsapp.action_report_chatroom_dashboard').report_action(self)

    def action_export_xlsx(self):
        self.ensure_one()
        data = self.get_report_data()
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        title = workbook.add_format({'bold': True, 'font_size': 16, 'font_color': '#714B67'})
        header = workbook.add_format({'bold': True, 'bg_color': '#714B67', 'font_color': 'white'})
        number = workbook.add_format({'num_format': '#,##0.00'})
        sheet = workbook.add_worksheet('Resumen')
        sheet.write('A1', 'Reporte gerencial de Chatroom', title)
        sheet.write('A2', 'Período'); sheet.write('B2', data.get('period_label'))
        sheet.write_row('A4', ['Indicador', 'Resultado'], header)
        summary = [
            ('Conversaciones de hoy', data.get('today_count', 0)),
            ('Conversaciones pendientes', data.get('pending_count', 0)),
            ('Mensajes sin leer', data.get('unread_total', 0)),
            ('Mensajes de hoy', data.get('messages_today', 0)),
            ('Primera respuesta promedio (min)', data.get('avg_first_response_minutes', 0)),
            ('Cumplimiento SLA (%)', data.get('sla_compliance_rate') or 0),
            ('Satisfacción promedio', data.get('avg_csat_score', 0)),
        ]
        for row, (label, value) in enumerate(summary, 4):
            sheet.write(row, 0, label); sheet.write(row, 1, value, number)
        sheet.set_column('A:A', 38); sheet.set_column('B:B', 20)
        stage_sheet = workbook.add_worksheet('Etapas')
        stage_sheet.write_row('A1', ['Etapa', 'Conversaciones', 'Sin leer'], header)
        for row, stage in enumerate(data.get('stage_breakdown', []), 1):
            stage_sheet.write_row(row, 0, [stage['name'], stage['count'], stage['unread_count']])
        stage_sheet.set_column('A:A', 28); stage_sheet.set_column('B:C', 16)
        kpi_sheet = workbook.add_worksheet('KPIs gerenciales')
        kpi_sheet.write_row('A1', ['KPI', 'Resultado', 'Objetivo', 'Estado'], header)
        for row, kpi in enumerate(data.get('custom_kpis', []), 1):
            kpi_sheet.write_row(row, 0, [kpi['name'], kpi['display_value'], kpi['target_display'], kpi['status']])
        kpi_sheet.set_column('A:A', 40); kpi_sheet.set_column('B:D', 20)
        workbook.close()
        attachment = self.env['ir.attachment'].create({
            'name': 'reporte_chatroom.xlsx', 'type': 'binary',
            'datas': base64.b64encode(output.getvalue()),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'res_model': self._name, 'res_id': self.id,
        })
        return {'type': 'ir.actions.act_url', 'url': f'/web/content/{attachment.id}?download=true', 'target': 'self'}

    def get_report_data(self):
        self.ensure_one()
        return self.env['chatroom.channel'].get_dashboard_data(
            int(self.period_days), agent_limit=20)


class ReportChatroomDashboard(models.AbstractModel):
    _name = 'report.chatroom_whatsapp.chatroom_dashboard_report'
    _description = 'Reporte PDF del dashboard de Chatroom'

    def _get_report_values(self, docids, data=None):
        docs = self.env['chatroom.dashboard.report.wizard'].browse(docids)
        wizard = docs[:1]
        return {
            'doc_ids': docids,
            'doc_model': 'chatroom.dashboard.report.wizard',
            'docs': docs,
            'wizard': wizard,
            'dashboard': wizard.get_report_data() if wizard else {},
            'company': wizard.company_id if wizard else self.env.company,
            'generated_at': fields.Datetime.now(),
        }

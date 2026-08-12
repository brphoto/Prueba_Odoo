# -*- coding: utf-8 -*-
import base64

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ManagementReportSubscription(models.Model):
    _name = 'management.report.subscription'
    _description = 'Suscripción de reportes gerenciales'
    _order = 'name'

    name = fields.Char(string='Nombre', required=True)
    active = fields.Boolean(default=True)
    report_type = fields.Selection([
        ('chatroom', 'Dashboard de Chatroom'),
        ('rfm', 'Inteligencia Comercial / RFM'),
    ], string='Reporte', required=True, default='chatroom')
    report_format = fields.Selection([
        ('pdf', 'PDF'), ('xlsx', 'Excel'),
    ], string='Formato', default='pdf', required=True)
    rfm_category = fields.Selection(
        selection='_selection_rfm_category_filter', string='Categoría RFM', default='all')
    period = fields.Selection([
        ('7', 'Últimos 7 días'), ('30', 'Últimos 30 días'),
        ('90', 'Últimos 90 días'), ('365', 'Últimos 12 meses'),
        ('all', 'Todo el historial'),
    ], default='30', required=True)
    frequency = fields.Selection([
        ('daily', 'Diario'), ('weekly', 'Semanal'), ('monthly', 'Mensual'),
    ], string='Frecuencia', required=True, default='weekly')
    recipient_ids = fields.Many2many(
        'res.partner', 'management_report_subscription_partner_rel',
        'subscription_id', 'partner_id', string='Destinatarios')
    next_run_at = fields.Datetime(
        string='Próximo envío', required=True,
        default=lambda self: fields.Datetime.now())
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company)
    last_sent_at = fields.Datetime(readonly=True)
    last_error = fields.Text(readonly=True)

    @api.model
    def _selection_rfm_category_filter(self):
        options = [('all', 'Todas')]
        try:
            options += self.env['res.partner']._selection_rfm_category()
        except Exception:
            options += [('a', 'A - Alto valor'), ('b', 'B - Valor medio'),
                        ('c', 'C - Bajo valor'), ('none', 'Sin historial')]
        return options

    @api.constrains('recipient_ids')
    def _check_recipients(self):
        for record in self:
            if record.recipient_ids and not record.recipient_ids.filtered('email'):
                raise UserError(_('Al menos un destinatario debe tener correo electrónico.'))

    def _render_report(self):
        self.ensure_one()
        if self.report_type == 'chatroom':
            wizard = self.env['chatroom.dashboard.report.wizard'].create({
                'period_days': '0' if self.period == 'all' else self.period,
                'company_id': self.company_id.id,
            })
            xmlid = 'chatroom_whatsapp.action_report_chatroom_dashboard'
            filename = 'reporte_chatroom.pdf'
        else:
            wizard = self.env['crm.rfm.dashboard.report.wizard'].create({
                'period': self.period if self.period in ('30', '90', '365', 'all') else '30',
                'category': self.rfm_category, 'company_id': self.company_id.id,
            })
            xmlid = 'crm_customer_intelligence.action_report_rfm_dashboard'
            filename = 'reporte_rfm.pdf'
        if self.report_format == 'xlsx':
            action = wizard.action_export_xlsx()
            attachment_id = int(action['url'].split('/web/content/')[1].split('?')[0])
            attachment = self.env['ir.attachment'].browse(attachment_id)
            return filename.replace('.pdf', '.xlsx'), base64.b64decode(attachment.datas)
        content, _report_type = self.env['ir.actions.report']._render_qweb_pdf(xmlid, wizard.ids)
        return filename, content

    def action_send_now(self):
        self.ensure_one()
        self._send_report()
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'title': _('Reporte enviado'),
            'message': _('El reporte fue enviado a los destinatarios configurados.'),
            'type': 'success',
        }}

    def _send_report(self):
        self.ensure_one()
        emails = self.recipient_ids.mapped('email')
        if not emails:
            raise UserError(_('Configura al menos un destinatario con correo electrónico.'))
        filename, pdf = self._render_report()
        attachment = self.env['ir.attachment'].sudo().create({
            'name': filename, 'type': 'binary', 'datas': base64.b64encode(pdf),
            'mimetype': 'application/pdf', 'res_model': self._name, 'res_id': self.id,
        })
        mail = self.env['mail.mail'].sudo().create({
            'subject': _('%s - %s') % (self.company_id.name, self.name),
            'body_html': _('<p>Adjunto encontrarás el reporte gerencial <strong>%s</strong>.</p>') % self.name,
            'email_from': self.company_id.email or self.env.user.email or 'noreply@localhost',
            'email_to': ','.join(emails), 'attachment_ids': [(4, attachment.id)],
        })
        mail.send(raise_exception=False)
        if mail.state != 'sent':
            raise UserError(_('El correo no se pudo enviar: %s') % (mail.failure_reason or mail.state))
        self.write({'last_sent_at': fields.Datetime.now(), 'last_error': False})
        return True

    def _schedule_next_run(self):
        self.ensure_one()
        days = {'daily': 1, 'weekly': 7, 'monthly': 30}[self.frequency]
        self.next_run_at = fields.Datetime.add(fields.Datetime.now(), days=days)

    @api.model
    def _cron_send_scheduled_reports(self):
        now = fields.Datetime.now()
        for subscription in self.search([('active', '=', True), ('next_run_at', '<=', now)]):
            try:
                subscription._send_report()
                subscription._schedule_next_run()
            except Exception as exc:  # noqa: BLE001
                subscription.write({
                    'last_error': str(exc),
                    'next_run_at': fields.Datetime.add(now, hours=1),
                })

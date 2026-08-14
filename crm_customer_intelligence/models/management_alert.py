# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class CrmManagementAlert(models.Model):
    _name = 'crm.management.alert'
    _description = 'Alerta gerencial comercial'
    _order = 'severity desc, alert_date desc, id desc'

    name = fields.Char(string='Alerta', required=True)
    alert_type = fields.Selection([
        ('lead_stagnant', 'Oportunidad estancada'),
        ('rfm_risk', 'Cliente RFM en riesgo'),
        ('invoice_overdue', 'Factura vencida'),
    ], string='Tipo', required=True)
    severity = fields.Selection([
        ('info', 'Informativa'), ('warning', 'Preventiva'), ('danger', 'Crítica'),
    ], string='Prioridad', required=True, default='warning')
    state = fields.Selection([
        ('unread', 'Sin revisar'), ('read', 'Revisada'), ('closed', 'Cerrada'),
    ], string='Estado', required=True, default='unread')
    alert_date = fields.Datetime(default=fields.Datetime.now, required=True)
    user_id = fields.Many2one('res.users', string='Responsable', default=lambda self: self.env.user)
    partner_id = fields.Many2one('res.partner', string='Contacto')
    lead_id = fields.Many2one('crm.lead', string='Oportunidad')
    source_model = fields.Char(readonly=True)
    source_res_id = fields.Integer(readonly=True)
    detail = fields.Text(string='Detalle')

    _source_unique = models.Constraint(
        'unique(alert_type, source_model, source_res_id)',
        'Ya existe una alerta para este registro y tipo.')

    def action_mark_read(self):
        self.write({'state': 'read'})

    def action_close(self):
        self.write({'state': 'closed'})

    def action_open_source(self):
        self.ensure_one()
        if not self.source_model or not self.source_res_id or self.source_model not in self.env:
            return False
        return {
            'type': 'ir.actions.act_window', 'res_model': self.source_model,
            'res_id': self.source_res_id, 'view_mode': 'form', 'target': 'current',
        }

    @api.model
    def get_my_counts(self):
        domain = [('state', 'in', ('unread', 'read'))]
        alerts = self.search(domain)
        return {
            'total': len(alerts),
            'danger': len(alerts.filtered(lambda alert: alert.severity == 'danger')),
            'warning': len(alerts.filtered(lambda alert: alert.severity == 'warning')),
        }

    @api.model
    def _upsert(self, vals):
        alert = self.search([
            ('alert_type', '=', vals['alert_type']),
            ('source_model', '=', vals['source_model']),
            ('source_res_id', '=', vals['source_res_id']),
        ], limit=1)
        if alert:
            if alert.state == 'closed':
                alert.write({'state': 'unread', 'alert_date': fields.Datetime.now(), **vals})
            return alert
        return self.create(vals)

    @api.model
    def _cron_generate_alerts(self):
        Lead = self.env['crm.lead']
        for lead in Lead.search([('active', '=', True), ('stage_id.is_won', '=', False)]):
            if lead.management_alert_state == 'red':
                self._upsert({
                    'name': _('Oportunidad estancada: %s') % lead.name,
                    'alert_type': 'lead_stagnant', 'severity': 'danger',
                    'partner_id': lead.partner_id.id, 'lead_id': lead.id,
                    'source_model': 'crm.lead', 'source_res_id': lead.id,
                    'detail': _('Lleva %s días sin gestión.') % lead.days_since_last_management,
                    'user_id': lead.user_id.id or self.env.user.id,
                })
        Category = self.env['crm.rfm.segment']
        risk_codes = Category.search([
            ('definition_type', '=', 'category'), ('active', '=', True),
            ('is_at_risk', '=', True),
        ]).mapped('code')
        if risk_codes:
            for partner in self.env['res.partner'].search([('rfm_category', 'in', risk_codes)]):
                self._upsert({
                    'name': _('Cliente RFM en riesgo: %s') % partner.name,
                    'alert_type': 'rfm_risk', 'severity': 'warning',
                    'partner_id': partner.id, 'source_model': 'res.partner',
                    'source_res_id': partner.id,
                    'detail': _('Revisar la última compra y programar seguimiento.'),
                })
        today = fields.Date.context_today(self)
        overdue = self.env['account.move'].search([
            ('move_type', '=', 'out_invoice'), ('state', '=', 'posted'),
            ('payment_state', '!=', 'paid'), ('invoice_date_due', '<', today),
        ])
        for invoice in overdue:
            self._upsert({
                'name': _('Factura vencida: %s') % invoice.name,
                'alert_type': 'invoice_overdue', 'severity': 'danger',
                'partner_id': invoice.partner_id.id, 'source_model': 'account.move',
                'source_res_id': invoice.id,
                'detail': _('Saldo pendiente: %s') % invoice.amount_residual,
            })

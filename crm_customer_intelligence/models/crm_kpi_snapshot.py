# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class CrmKpiSnapshot(models.Model):
    _name = 'crm.kpi.snapshot'
    _description = 'Histórico diario de KPI comercial'
    _order = 'snapshot_date desc, kpi_id'

    snapshot_date = fields.Date(required=True, default=fields.Date.context_today)
    kpi_id = fields.Many2one('crm.kpi.definition', required=True, ondelete='cascade')
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    period = fields.Selection([('30', '30 días'), ('90', '90 días')], default='90', required=True)
    value = fields.Float()
    display_value = fields.Char()
    target_value = fields.Float()
    status = fields.Selection([
        ('neutral', 'Sin objetivo'), ('success', 'Cumplido'), ('danger', 'En riesgo'),
    ], default='neutral')

    _snapshot_unique = models.Constraint(
        'unique(snapshot_date, kpi_id, company_id, period)',
        'Ya existe un histórico para este KPI, fecha y período.',
    )

    @api.model
    def _cron_compute_snapshots(self):
        env = self.env
        today = fields.Date.context_today(env['crm.kpi.snapshot'])
        for kpi in env['crm.kpi.definition'].search([('active', '=', True)]):
            result = kpi._compute_value('90', 'all')
            snapshot = env['crm.kpi.snapshot'].search([
                ('snapshot_date', '=', today), ('kpi_id', '=', kpi.id),
                ('company_id', '=', env.company.id), ('period', '=', '90'),
            ], limit=1)
            vals = {
                'value': result['value'], 'display_value': result['display_value'],
                'target_value': result['target_value'], 'status': result['status'],
            }
            if snapshot:
                snapshot.write(vals)
            else:
                env['crm.kpi.snapshot'].create({
                    'snapshot_date': today, 'kpi_id': kpi.id,
                    'company_id': env.company.id, 'period': '90', **vals,
                })

    @api.model
    def _cron_notify_red_kpis(self):
        activity_type = self.env['mail.activity.type'].search(
            [('category', '=', 'default')], order='sequence, id', limit=1)
        managers = self.env.ref('sales_team.group_sale_manager').all_user_ids.filtered('active')
        model_id = self.env['ir.model']._get_id('crm.kpi.definition')
        for kpi in self.env['crm.kpi.definition'].search([('active', '=', True)]):
            result = kpi._compute_value('90', 'all')
            if result['status'] != 'danger' or not activity_type:
                continue
            summary = _('KPI comercial en riesgo: %s') % kpi.name
            exists = self.env['mail.activity'].search([
                ('res_model_id', '=', model_id), ('res_id', '=', kpi.id),
                ('summary', '=', summary), ('user_id', 'in', managers.ids),
            ], limit=1)
            if exists:
                continue
            self.env['mail.activity'].create([{
                'activity_type_id': activity_type.id,
                'summary': summary,
                'note': _('Resultado actual: %s. Objetivo: %s.') % (
                    result['display_value'], result['target_display']),
                'date_deadline': fields.Date.context_today(self),
                'user_id': user.id,
                'res_model_id': model_id,
                'res_id': kpi.id,
            } for user in managers])

# -*- coding: utf-8 -*-
from odoo import api, fields, models


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

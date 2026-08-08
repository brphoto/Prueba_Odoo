# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ChatroomKpiSnapshot(models.Model):
    _name = 'chatroom.kpi.snapshot'
    _description = 'Histórico diario de KPI de Chatroom'
    _order = 'snapshot_date desc, kpi_id'

    snapshot_date = fields.Date(required=True, default=fields.Date.context_today)
    kpi_id = fields.Many2one('chatroom.kpi.definition', required=True, ondelete='cascade')
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    period_days = fields.Integer(default=30)
    value = fields.Float()
    display_value = fields.Char()
    target_value = fields.Float()
    status = fields.Selection([
        ('neutral', 'Sin objetivo'), ('success', 'Cumplido'), ('danger', 'En riesgo'),
    ], default='neutral')

    _snapshot_unique = models.Constraint(
        'unique(snapshot_date, kpi_id, company_id, period_days)',
        'Ya existe un histórico para este KPI, fecha y período.',
    )

    @api.model
    def _cron_compute_snapshots(self):
        """Guarda el valor del período estándar y deja una serie temporal
        que puede graficarse o exportarse sin recalcular el pasado."""
        env = self.env
        today = fields.Date.context_today(env['chatroom.kpi.snapshot'])
        for kpi in env['chatroom.kpi.definition'].search([('active', '=', True)]):
            result = kpi._compute_value(30)
            snapshot = env['chatroom.kpi.snapshot'].search([
                ('snapshot_date', '=', today), ('kpi_id', '=', kpi.id),
                ('company_id', '=', env.company.id), ('period_days', '=', 30),
            ], limit=1)
            vals = {
                'value': result['value'], 'display_value': result['display_value'],
                'target_value': result['target_value'], 'status': result['status'],
            }
            if snapshot:
                snapshot.write(vals)
            else:
                env['chatroom.kpi.snapshot'].create({
                    'snapshot_date': today, 'kpi_id': kpi.id,
                    'company_id': env.company.id, 'period_days': 30, **vals,
                })

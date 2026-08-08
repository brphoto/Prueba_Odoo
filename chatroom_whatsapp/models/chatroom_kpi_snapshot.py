# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


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

    @api.model
    def _cron_notify_red_kpis(self):
        activity_type = self.env['mail.activity.type'].search(
            [('category', '=', 'default')], order='sequence, id', limit=1)
        manager_group = self.env.ref('chatroom_whatsapp.group_chatroom_manager', raise_if_not_found=False)
        managers = manager_group and self.env['res.users'].search([('group_ids', 'in', manager_group.id)]) or self.env.user
        model_id = self.env['ir.model']._get_id('chatroom.kpi.definition')
        for kpi in self.env['chatroom.kpi.definition'].search([('active', '=', True)]):
            result = kpi._compute_value(30)
            if result['status'] != 'danger' or not activity_type:
                continue
            summary = _('KPI en riesgo: %s') % kpi.name
            exists = self.env['mail.activity'].search([
                ('res_model_id', '=', model_id), ('res_id', '=', kpi.id),
                ('summary', '=', summary), ('user_id', 'in', managers.ids),
            ], limit=1)
            if exists:
                continue
            self.env['mail.activity'].create([{
                'activity_type_id': activity_type.id,
                'summary': summary,
                'note': _('El KPI está fuera de su objetivo. Resultado actual: %s. Objetivo: %s.') % (
                    result['display_value'], result['target_display']),
                'date_deadline': fields.Date.context_today(self),
                'user_id': user.id,
                'res_model_id': model_id,
                'res_id': kpi.id,
            } for user in managers])

# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CrmLeadPurgeWizard(models.TransientModel):
    _name = 'crm.lead.purge.wizard'
    _description = 'Depuración controlada de oportunidades estancadas'

    stagnation_filter = fields.Selection([
        ('all_stagnant', 'Todas las estancadas'),
        ('dead_only', 'Solo muertas'),
        ('below_score', 'Score real/ficticia menor o igual a'),
        ('manual', 'Selección manual'),
    ], string='Filtro', required=True, default='all_stagnant')
    score_threshold = fields.Float(string='Score máximo', default=20.0)
    action = fields.Selection([
        ('lose', 'Cerrar como perdida'),
        ('downgrade', 'Degradar a lead'),
        ('archive', 'Archivar'),
        ('assign_review', 'Asignar a revisor'),
    ], string='Acción', required=True, default='assign_review')
    loss_reason = fields.Many2one('crm.lost.reason', string='Motivo de pérdida')
    reviewer_id = fields.Many2one('res.users', string='Revisor')
    create_activities = fields.Boolean(string='Crear actividades', default=True)
    notify_owners = fields.Boolean(string='Notificar propietarios', default=True)
    selected_lead_ids = fields.Many2many('crm.lead', string='Oportunidades seleccionadas')
    total_opportunities = fields.Integer(string='Oportunidades', compute='_compute_summary')
    total_capital_released = fields.Monetary(
        string='Capital a liberar', currency_field='company_currency', compute='_compute_summary')
    avg_real_score = fields.Float(string='Score real/ficticia promedio', compute='_compute_summary')
    company_currency = fields.Many2one('res.currency', related='company_id.currency_id', readonly=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True)

    @api.model
    def default_get(self, field_list):
        values = super().default_get(field_list)
        active_ids = self.env.context.get('active_ids') or []
        if active_ids:
            values['selected_lead_ids'] = [(6, 0, active_ids)]
            values['stagnation_filter'] = 'manual'
        return values

    def _get_target_leads(self):
        self.ensure_one()
        Lead = self.env['crm.lead']
        if self.stagnation_filter == 'manual':
            return self.selected_lead_ids.filtered(
                lambda lead: lead.active and lead.type == 'opportunity' and not lead.stage_id.is_won)
        domain = [
            ('active', '=', True), ('type', '=', 'opportunity'),
            ('stage_id.is_won', '=', False), ('probability', '<', 100),
        ]
        if self.stagnation_filter == 'all_stagnant':
            domain.append(('stagnation_score', 'in', ('critical', 'stagnant', 'dead')))
        elif self.stagnation_filter == 'dead_only':
            domain.append(('stagnation_score', '=', 'dead'))
        elif self.stagnation_filter == 'below_score':
            domain.append(('real_vs_fake_score', '<=', self.score_threshold))
        return Lead.search(domain)

    @api.depends('stagnation_filter', 'score_threshold', 'selected_lead_ids')
    def _compute_summary(self):
        for wizard in self:
            leads = wizard._get_target_leads()
            wizard.total_opportunities = len(leads)
            wizard.total_capital_released = sum(leads.mapped('estimated_capital_trapped'))
            wizard.avg_real_score = sum(leads.mapped('real_vs_fake_score')) / len(leads) if leads else 0

    def action_open(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'res_model': self._name,
            'res_id': self.id, 'views': [(False, 'form')], 'target': 'new',
        }

    def action_preview(self):
        self.ensure_one()
        self._compute_summary()
        return self.action_open()

    def action_execute_purge(self):
        self.ensure_one()
        if not self.env.user.has_group('crm_stagnation_management.group_crm_stagnation_manager'):
            raise UserError(_('Solo un administrador de estancamiento puede ejecutar la depuración.'))
        leads = self._get_target_leads()
        if not leads:
            raise UserError(_('No se encontraron oportunidades para depurar.'))
        if self.action == 'lose' and not self.loss_reason:
            raise UserError(_('Seleccione un motivo de pérdida antes de cerrar oportunidades.'))
        if self.action == 'assign_review' and not self.reviewer_id:
            raise UserError(_('Seleccione el revisor que recibirá las oportunidades.'))
        executed = 0
        released = 0.0
        for lead in leads:
            capital = lead.estimated_capital_trapped
            if self.action == 'lose':
                lead.action_set_lost(lost_reason=self.loss_reason)
            elif self.action == 'downgrade':
                lead.with_context(skip_stagnation_recompute=True).write({
                    'type': 'lead', 'probability': 0, 'stagnation_processed_at': fields.Datetime.now(),
                })
            elif self.action == 'archive':
                lead.with_context(skip_stagnation_recompute=True).write({
                    'active': False, 'stagnation_processed_at': fields.Datetime.now(),
                })
            elif self.action == 'assign_review':
                lead.with_context(skip_stagnation_recompute=True).write({
                    'user_id': self.reviewer_id.id, 'stagnation_processed_at': fields.Datetime.now(),
                })
            if self.create_activities:
                user_id = self.reviewer_id.id if self.action == 'assign_review' else (lead.user_id.id or self.env.user.id)
                lead.activity_schedule(
                    'mail.mail_activity_data_todo', user_id=user_id,
                    summary='CRM: revisar depuración de oportunidad',
                    note=_('Score real/ficticia: %.1f%%. Capital estimado: %.2f.') % (lead.real_vs_fake_score, capital))
            if self.notify_owners and lead.user_id and lead.user_id.partner_id:
                lead.message_post(
                    body=_('[CRM-SYSTEM] La oportunidad %s fue procesada mediante el flujo de depuración.') % lead.display_name,
                    partner_ids=[lead.user_id.partner_id.id], message_type='notification', subtype_xmlid='mail.mt_note')
            executed += 1
            released += capital
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'title': _('Depuración completada'),
                'message': _('Se procesaron %s oportunidades. Capital liberado estimado: %.2f.') % (executed, released),
                'type': 'success', 'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

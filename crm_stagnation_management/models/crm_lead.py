# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    days_in_stage = fields.Integer(string='Días en etapa actual', readonly=True, index=True)
    last_activity_date = fields.Datetime(string='Última gestión humana', readonly=True, index=True)
    days_without_activity = fields.Integer(string='Días sin actividad', readonly=True, index=True)
    max_days_allowed = fields.Integer(
        string='Días máximos permitidos', related='stage_id.stagnation_max_days', readonly=True)
    days_over_limit = fields.Integer(string='Días sobre el límite', readonly=True)
    stagnation_score = fields.Selection([
        ('healthy', 'Saludable'), ('warning', 'Precaución'), ('critical', 'Crítico'),
        ('stagnant', 'Estancada'), ('dead', 'Muerta'),
    ], string='Nivel de estancamiento', default='healthy', index=True, readonly=True)
    estimated_capital_trapped = fields.Monetary(
        string='Capital estimado atrapado', currency_field='company_currency', readonly=True)
    next_action_required = fields.Text(string='Próxima acción requerida', readonly=True)
    stagnation_reason = fields.Selection([
        ('no_response', 'Sin respuesta del cliente'),
        ('no_proposal', 'Sin propuesta enviada'),
        ('price_disagreement', 'Desacuerdo en precio'),
        ('competitor', 'Competidor en juego'),
        ('budget', 'Sin presupuesto aprobado'),
        ('decision_maker', 'Sin acceso al decisor'),
        ('lost_interest', 'Interés perdido'),
        ('fake_opportunity', 'Oportunidad ficticia'),
        ('other', 'Otro'),
    ], string='Motivo de estancamiento')
    real_vs_fake_score = fields.Float(
        string='Score real vs. ficticia (%)', readonly=True,
        help='0% representa una oportunidad probablemente ficticia; 100% representa una oportunidad con señales reales.')
    purge_recommendation = fields.Selection([
        ('keep', 'Mantener - Alta probabilidad'),
        ('push', 'Forzar avance - Requiere acción'),
        ('review', 'Revisar - Duda razonable'),
        ('downgrade', 'Degradar a lead'),
        ('purge', 'Depurar - Cerrar como pérdida'),
    ], string='Recomendación de depuración', readonly=True)
    stagnation_detected_at = fields.Datetime(string='Detectada el', readonly=True)
    stagnation_notified_at = fields.Datetime(string='Última alerta', readonly=True)
    stagnation_escalated_at = fields.Datetime(string='Último escalamiento', readonly=True)
    stagnation_processed_at = fields.Datetime(string='Última depuración', readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        leads = super().create(vals_list)
        leads._recompute_stagnation_values()
        return leads

    def write(self, vals):
        result = super().write(vals)
        if not self.env.context.get('skip_stagnation_recompute') and any(
            field in vals for field in ('stage_id', 'expected_revenue', 'probability', 'active', 'partner_id', 'user_id')
        ):
            self._recompute_stagnation_values()
        return result

    def _stagnation_last_activity(self):
        self.ensure_one()
        candidates = [self.date_last_stage_update or self.create_date]
        messages = self.message_ids.filtered(
            lambda message: message.message_type in ('comment', 'email', 'email_outgoing')
            and not (message.body or '').startswith('[CRM-SYSTEM]'))
        last_message = messages.sorted('date', reverse=True)[:1]
        if last_message:
            candidates.append(last_message.date)
        activities = self.activity_ids.filtered(
            lambda activity: not (activity.summary or '').startswith('CRM:'))
        last_activity = activities.sorted('create_date', reverse=True)[:1]
        if last_activity:
            candidates.append(last_activity.create_date or last_activity.date_deadline)
        return max((value for value in candidates if value), default=fields.Datetime.now())

    def _stagnation_values(self, config):
        self.ensure_one()
        now = fields.Datetime.to_datetime(fields.Datetime.now())
        stage_date = fields.Datetime.to_datetime(self.date_last_stage_update or self.create_date or now)
        last_activity = fields.Datetime.to_datetime(self._stagnation_last_activity())
        days_in_stage = max((now - stage_date).days, 0)
        days_without_activity = max((now - last_activity).days, 0)
        max_days = max(self.stage_id.stagnation_max_days or config.default_max_days or 1, 1)
        ratio = days_in_stage / max_days
        if days_without_activity >= max_days * config.dead_no_activity_ratio or ratio >= config.dead_ratio:
            level = 'dead'
        elif ratio >= config.stagnant_ratio:
            level = 'stagnant'
        elif ratio >= config.critical_ratio:
            level = 'critical'
        elif ratio >= config.warning_ratio:
            level = 'warning'
        else:
            level = 'healthy'

        activities = self.activity_ids.filtered(
            lambda activity: not (activity.summary or '').startswith('CRM:'))
        activity_count = len(activities) + len(self.message_ids.filtered(
            lambda message: message.message_type in ('comment', 'email', 'email_outgoing')
            and not (message.body or '').startswith('[CRM-SYSTEM]')))
        activity_rate = activity_count / days_in_stage if days_in_stage else 0
        if activity_rate >= config.high_activity_rate and days_without_activity <= 7:
            real_score = min(100.0, 80.0 + activity_rate * 20.0)
        elif activity_rate >= config.medium_activity_rate and days_without_activity <= 14:
            real_score = 50.0 + min(30.0, activity_rate * 30.0)
        elif activity_rate >= config.low_activity_rate:
            real_score = 20.0 + min(30.0, activity_rate * 30.0)
        else:
            real_score = max(0.0, 20.0 - days_without_activity)
        if self.stage_id.stagnation_required_activities and activity_count >= self.stage_id.stagnation_required_activities:
            real_score = min(100.0, real_score + 10.0)

        factors = {
            'warning': config.capital_warning_factor,
            'critical': config.capital_critical_factor,
            'stagnant': config.capital_stagnant_factor,
            'dead': config.capital_dead_factor,
        }
        trapped = (self.expected_revenue or 0.0) * factors.get(level, 0.0)
        if level == 'dead':
            recommendation = 'purge'
            action = 'Revisar hoy: confirmar motivo y cerrar, archivar o degradar la oportunidad.'
        elif level == 'stagnant':
            recommendation = 'purge' if real_score < config.min_score_to_purge else 'downgrade'
            action = 'Registrar el motivo y definir una decisión concreta con fecha.'
        elif level == 'critical':
            recommendation = 'review'
            action = 'Contactar al cliente y registrar una actividad de seguimiento inmediata.'
        elif level == 'warning':
            recommendation = 'push'
            action = 'Programar la próxima actividad antes de superar el límite de la etapa.'
        else:
            recommendation = 'keep'
            action = 'Continuar el seguimiento normal de la oportunidad.'
        return {
            'days_in_stage': days_in_stage,
            'last_activity_date': fields.Datetime.to_string(last_activity),
            'days_without_activity': days_without_activity,
            'days_over_limit': max(days_in_stage - max_days, 0),
            'stagnation_score': level,
            'estimated_capital_trapped': trapped,
            'next_action_required': action,
            'real_vs_fake_score': real_score,
            'purge_recommendation': recommendation,
        }

    def _recompute_stagnation_values(self):
        for company in self.mapped('company_id'):
            config = self.env['crm.stagnation.config'].get_for_company(company)
            leads = self.filtered(lambda lead: lead.company_id == company)
            for lead in leads:
                if not lead.active or lead.type != 'opportunity' or lead.stage_id.is_won or lead.probability >= 100:
                    values = {
                        'days_in_stage': 0, 'last_activity_date': False, 'days_without_activity': 0, 'days_over_limit': 0,
                        'stagnation_score': 'healthy', 'estimated_capital_trapped': 0,
                        'next_action_required': False, 'real_vs_fake_score': 0,
                        'purge_recommendation': 'keep', 'stagnation_detected_at': False,
                    }
                else:
                    values = lead._stagnation_values(config)
                    if lead.stagnation_score == 'healthy' and values['stagnation_score'] != 'healthy':
                        values['stagnation_detected_at'] = fields.Datetime.now()
                    elif values['stagnation_score'] == 'healthy':
                        values['stagnation_detected_at'] = False
                lead.with_context(
                    skip_stagnation_recompute=True, skip_stagnation_reason_check=True).write(values)
            config.sudo().write({'last_run': fields.Datetime.now(), 'last_count': len(leads)})
        return True

    def action_recompute_stagnation(self):
        self._recompute_stagnation_values()
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'title': _('Estancamiento actualizado'),
                       'message': _('%s oportunidades recalculadas.') % len(self),
                       'type': 'success', 'sticky': False},
        }

    @api.model
    def _cron_recompute_stagnation(self):
        leads = self.search([('active', '=', True), ('type', '=', 'opportunity'), ('stage_id.is_won', '=', False), ('probability', '<', 100)])
        leads._recompute_stagnation_values()
        return len(leads)

    def _should_notify(self, config):
        self.ensure_one()
        if not config.notify_enabled or not self.user_id:
            return False
        if config.level_rank(self.stagnation_score) < config.level_rank(config.notification_level):
            return False
        if not self.stagnation_notified_at:
            return True
        next_date = fields.Datetime.add(self.stagnation_notified_at, days=max(config.notification_repeat_days, 1))
        return fields.Datetime.now() >= next_date

    def _create_optional_ai_task(self, config):
        if not config.create_ai_tasks or 'chatroom.ai.task' not in self.env or 'chatroom.channel' not in self.env:
            return False
        if config.level_rank(self.stagnation_score) < config.level_rank(config.ai_task_level):
            return False
        channel = self.env['chatroom.channel'].search([('pinned_lead_id', '=', self.id)], limit=1)
        if not channel:
            return False
        duplicate = self.env['chatroom.ai.task'].search_count([
            ('channel_id', '=', channel.id), ('task_type', '=', 'followup'),
            ('state', 'in', ('draft', 'awaiting_approval', 'planned', 'running')),
        ])
        if duplicate:
            return False
        self.env['chatroom.ai.task'].sudo().create_from_channel(
            channel, task_type='followup',
            prompt=_('Revisar oportunidad estancada: %s. Motivo: %s. Recomienda una acción comercial concreta sin enviarla.') % (
                self.display_name, dict(self._fields['stagnation_reason'].selection).get(self.stagnation_reason, 'Pendiente')))
        return True

    @api.model
    def _cron_notify_stagnation(self):
        leads = self.search([
            ('active', '=', True), ('type', '=', 'opportunity'),
            ('stage_id.is_won', '=', False), ('probability', '<', 100),
            ('stagnation_score', 'in', ('warning', 'critical', 'stagnant', 'dead')),
        ])
        notified = escalated = ai_tasks = 0
        for lead in leads:
            config = self.env['crm.stagnation.config'].get_for_company(lead.company_id)
            if lead._should_notify(config):
                lead.message_post(
                    body=_('[CRM-SYSTEM] Oportunidad estancada: %(name)s. Nivel: %(level)s. Días en etapa: %(days)s. Capital atrapado: %(capital).2f. Próxima acción: %(action)s') % {
                        'name': lead.display_name, 'level': dict(lead._fields['stagnation_score'].selection).get(lead.stagnation_score),
                        'days': lead.days_in_stage, 'capital': lead.estimated_capital_trapped, 'action': lead.next_action_required,
                    }, partner_ids=[lead.user_id.partner_id.id], message_type='notification', subtype_xmlid='mail.mt_note')
                lead.activity_schedule(
                    'mail.mail_activity_data_todo', user_id=lead.user_id.id,
                    summary='CRM: atender oportunidad estancada', note=lead.next_action_required)
                lead.with_context(skip_stagnation_recompute=True).write({'stagnation_notified_at': fields.Datetime.now()})
                notified += 1
            if config.escalation_enabled and lead.days_over_limit >= config.escalation_after_days and not lead.stagnation_escalated_at:
                leader = lead.user_id.parent_id or lead.team_id.user_id
                if leader and leader != lead.user_id:
                    lead.activity_schedule(
                        'mail.mail_activity_data_todo', user_id=leader.id,
                        summary='CRM: escalamiento de oportunidad estancada',
                        note=_('Revisar %(lead)s. Nivel %(level)s, score real/ficticia %(score).1f%% y capital atrapado %(capital).2f.') % {
                            'lead': lead.display_name, 'level': lead.stagnation_score,
                            'score': lead.real_vs_fake_score, 'capital': lead.estimated_capital_trapped,
                        })
                    lead.with_context(skip_stagnation_recompute=True).write({'stagnation_escalated_at': fields.Datetime.now()})
                    escalated += 1
            if lead._create_optional_ai_task(config):
                ai_tasks += 1
        return {'notified': notified, 'escalated': escalated, 'ai_tasks': ai_tasks}

    @api.constrains('stagnation_score', 'stagnation_reason')
    def _check_stagnation_reason(self):
        for lead in self:
            config = self.env['crm.stagnation.config'].get_for_company(lead.company_id)
            if (not self.env.context.get('skip_stagnation_reason_check') and config.require_reason
                    and lead.stagnation_score in ('critical', 'stagnant', 'dead') and not lead.stagnation_reason):
                raise ValidationError(_('Debe especificar el motivo de estancamiento antes de continuar.'))

    def action_open_purge_wizard(self):
        return self.env['crm.lead.purge.wizard'].with_context(active_ids=self.ids).create({}).action_open()

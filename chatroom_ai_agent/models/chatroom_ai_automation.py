# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ChatroomAiAutomation(models.Model):
    _name = 'chatroom.ai.automation'
    _description = 'Automatización del agente IA'
    _order = 'sequence, name'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    trigger = fields.Selection([
        ('daily_review', 'Revisión periódica'),
        ('open_conversation', 'Conversación activa'),
        ('open_opportunity', 'Oportunidad abierta'),
        ('pending_quote', 'Cotización pendiente'),
        ('pending_activity', 'Actividad vencida'),
        ('overdue_invoice', 'Factura pendiente'),
    ], required=True, default='daily_review')
    task_type = fields.Selection([
        ('orchestrate', 'Orquestar solicitud'),
        ('classify_customer', 'Clasificar cliente'),
        ('qualify_lead', 'Calificar oportunidad'),
        ('prepare_reply', 'Preparar respuesta'),
        ('followup', 'Preparar seguimiento'),
        ('collect_payment', 'Preparar cobranza'),
        ('sales_conversion', 'Convertir conversación en venta'),
        ('daily_review', 'Revisión diaria'),
    ], string='Tipo de tarea', required=True, default='daily_review')
    approval_required = fields.Boolean(default=True)
    max_tasks = fields.Integer(default=20)
    max_attempts = fields.Integer(
        string='Intentos máximos por tarea', default=3,
        help='Cantidad máxima de ejecuciones antes de dejar una tarea bloqueada para revisión humana.')
    only_unread = fields.Boolean(string='Solo conversaciones no leídas')
    only_unassigned = fields.Boolean(string='Solo conversaciones sin asignar')
    min_rfm_score = fields.Integer(string='Score RFM mínimo', default=0)
    instruction = fields.Text(string='Instrucción para la IA', help='Contexto adicional que se agregará a la tarea creada.')
    last_run = fields.Datetime(readonly=True)
    last_run_count = fields.Integer(string='Tareas creadas en la última ejecución', readonly=True)
    last_error = fields.Text(string='Último error', readonly=True)
    last_scanned_count = fields.Integer(string='Canales revisados', readonly=True)
    last_skipped_count = fields.Integer(string='Canales omitidos', readonly=True)
    last_run_summary = fields.Char(string='Resumen de la última ejecución', readonly=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, index=True)

    @api.constrains('max_tasks', 'max_attempts', 'min_rfm_score')
    def _check_limits(self):
        for automation in self:
            if automation.max_tasks <= 0:
                raise ValidationError(_('El máximo de tareas debe ser mayor que cero.'))
            if automation.max_attempts <= 0:
                raise ValidationError(_('Los intentos máximos deben ser mayores que cero.'))
            if automation.min_rfm_score < 0:
                raise ValidationError(_('El score RFM mínimo no puede ser negativo.'))

    @api.model
    def _channels_for(self, automation):
        if 'chatroom.channel' not in self.env:
            return self.env['chatroom.channel']
        company = automation.company_id or self.env.company
        domain = [
            ('state', 'in', ('open', 'pending')),
            ('company_id', '=', company.id),
        ]
        if automation.trigger == 'open_conversation':
            recent_from = fields.Datetime.to_datetime(fields.Datetime.now()) - timedelta(hours=24)
            domain.append(('write_date', '>=', recent_from))
        elif automation.trigger == 'open_opportunity':
            if 'crm.lead' not in self.env:
                return self.env['chatroom.channel']
            partner_ids = self.env['crm.lead'].sudo().search([
                ('type', '=', 'opportunity'), ('active', '=', True),
                ('probability', '<', 100),
                ('company_id', '=', company.id),
            ], order='write_date desc, id desc', limit=max(automation.max_tasks or 20, 1) * 5).mapped('partner_id').ids
            domain.append(('partner_id', 'in', partner_ids or [0]))
        elif automation.trigger == 'pending_quote':
            if 'sale.order' not in self.env:
                return self.env['chatroom.channel']
            partner_ids = self.env['sale.order'].sudo().search([
                ('state', 'in', ('draft', 'sent')),
                ('company_id', '=', company.id),
            ], order='date_order desc, id desc', limit=max(automation.max_tasks or 20, 1) * 5).mapped('partner_id').ids
            domain.append(('partner_id', 'in', partner_ids or [0]))
        elif automation.trigger == 'pending_activity':
            if 'mail.activity' not in self.env or 'ir.model' not in self.env:
                return self.env['chatroom.channel']
            model = self.env['ir.model']._get('chatroom.channel')
            activity_domain = [('res_model_id', '=', model.id)]
            if 'date_deadline' in self.env['mail.activity']._fields:
                activity_domain.append(('date_deadline', '<=', fields.Date.context_today(self)))
            channel_ids = self.env['mail.activity'].sudo().search(
                activity_domain,
                order='date_deadline asc, id desc',
                limit=max(automation.max_tasks or 20, 1) * 5,
            ).mapped('res_id')
            domain.append(('id', 'in', channel_ids or [0]))
        elif automation.trigger == 'overdue_invoice':
            if 'account.move' not in self.env:
                return self.env['chatroom.channel']
            partner_ids = self.env['account.move'].sudo().search([
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
                ('payment_state', 'in', ('not_paid', 'partial')),
                ('invoice_date_due', '<', fields.Date.context_today(self)),
                ('company_id', '=', company.id),
            ]).mapped('partner_id').ids
            domain.append(('partner_id', 'in', partner_ids or [0]))
        configured_raw = self.env['ir.config_parameter'].sudo().get_param(
            'chatroom_ai_agent.max_tasks', automation.max_tasks or 20)
        try:
            configured_limit = max(int(configured_raw), 1)
        except (TypeError, ValueError):
            configured_limit = max(automation.max_tasks or 20, 1)
        channels = self.env['chatroom.channel'].sudo().search(
            domain, limit=min(automation.max_tasks or configured_limit, configured_limit))
        if automation.only_unread:
            channels = channels.filtered(lambda channel: channel.unread_count > 0)
        if automation.only_unassigned:
            channels = channels.filtered(lambda channel: not channel.assigned_user_id)
        if automation.min_rfm_score and 'rfm_score' in self.env['res.partner']._fields:
            channels = channels.filtered(lambda channel: channel.partner_id and channel.partner_id.rfm_score >= automation.min_rfm_score)
        return channels

    def action_run_now(self):
        self.ensure_one()
        channels = self._channels_for(self)
        created = self._run_for_channels(channels)
        skipped = max(len(channels) - created, 0)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Automatización ejecutada'),
                'message': _('%s tarea(s) creada(s) de %s canal(es) revisado(s); %s omitido(s).') % (
                    created, len(channels), skipped),
                'type': 'success' if created else 'warning',
                'sticky': False,
            },
        }

    def _run_for_channels(self, channels):
        self.ensure_one()
        tasks = self.env['chatroom.ai.task'].sudo()
        created = 0
        errors = []
        for channel in channels:
            try:
                with self.env.cr.savepoint():
                    duplicate = tasks.search_count([
                        ('channel_id', '=', channel.id),
                        ('task_type', '=', self.task_type or 'daily_review'),
                        ('state', 'in', ('awaiting_approval', 'planned', 'running')),
                    ])
                    if duplicate:
                        continue
                    instruction = self.instruction or (_('Automatización: %s') % self.name)
                    template = getattr(self, 'template_id', False)
                    if template:
                        instruction = '%s\n\nMensaje personalizado preparado:\n%s' % (
                            instruction, template.render(channel=channel))
                    task = tasks.create_from_channel(
                        channel, self.task_type or 'daily_review', instruction,
                        self.approval_required, automation=self)
                    task.action_plan()
                    if not self.approval_required and task.state == 'planned':
                        task.action_run()
                    created += 1
            except Exception as exc:
                errors.append('%s: %s' % (channel.display_name, exc))
        self.write({
            'last_run': fields.Datetime.now(),
            'last_run_count': created,
            'last_scanned_count': len(channels),
            'last_skipped_count': max(len(channels) - created, 0),
            'last_run_summary': _('%s creadas · %s revisadas · %s omitidas') % (
                created, len(channels), max(len(channels) - created, 0)),
            'last_error': '\n'.join(errors)[:4000] or False,
        })
        return created

    @api.model
    def _cron_run_scheduled(self):
        enabled = self.env['ir.config_parameter'].sudo().get_param(
            'chatroom_ai_agent.enabled', 'False') == 'True'
        if not enabled:
            return 0
        total = 0
        for automation in self.sudo().search([('active', '=', True), ('trigger', 'in', ('daily_review', 'open_conversation', 'open_opportunity', 'pending_quote', 'pending_activity', 'overdue_invoice'))]):
            try:
                total += automation._run_for_channels(automation._channels_for(automation))
            except Exception as exc:
                self.env.cr.rollback()
                automation.write({'last_run': fields.Datetime.now(), 'last_error': str(exc)[:4000]})
        return total

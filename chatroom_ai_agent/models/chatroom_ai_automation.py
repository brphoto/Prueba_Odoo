# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, api, fields, models


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
        ('overdue_invoice', 'Factura pendiente'),
    ], required=True, default='daily_review')
    task_type = fields.Selection([
        ('orchestrate', 'Orquestar solicitud'),
        ('classify_customer', 'Clasificar cliente'),
        ('qualify_lead', 'Calificar oportunidad'),
        ('prepare_reply', 'Preparar respuesta'),
        ('followup', 'Preparar seguimiento'),
        ('collect_payment', 'Preparar cobranza'),
        ('daily_review', 'Revisión diaria'),
    ], string='Tipo de tarea', required=True, default='daily_review')
    approval_required = fields.Boolean(default=True)
    max_tasks = fields.Integer(default=20)
    last_run = fields.Datetime(readonly=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, index=True)

    @api.model
    def _channels_for(self, automation):
        if 'chatroom.channel' not in self.env:
            return self.env['chatroom.channel']
        domain = [('state', 'in', ('open', 'pending'))]
        if automation.trigger == 'open_conversation':
            domain.append(('write_date', '>=', fields.Datetime.now() - timedelta(hours=24)))
        configured_limit = int(self.env['ir.config_parameter'].sudo().get_param(
            'chatroom_ai_agent.max_tasks', automation.max_tasks or 20))
        return self.env['chatroom.channel'].sudo().search(
            domain, limit=min(automation.max_tasks or configured_limit, configured_limit))

    def action_run_now(self):
        self.ensure_one()
        return self._run_for_channels(self._channels_for(self))

    def _run_for_channels(self, channels):
        self.ensure_one()
        tasks = self.env['chatroom.ai.task'].sudo()
        created = 0
        for channel in channels:
            duplicate = tasks.search_count([('channel_id', '=', channel.id), ('task_type', '=', self.task_type or 'daily_review'), ('state', 'in', ('awaiting_approval', 'planned', 'running'))])
            if duplicate:
                continue
            task = tasks.create_from_channel(channel, self.task_type or 'daily_review', _('Automatización: %s') % self.name, self.approval_required)
            task.action_plan()
            if not self.approval_required:
                task.action_run()
            created += 1
        self.write({'last_run': fields.Datetime.now()})
        return created

    @api.model
    def _cron_run_scheduled(self):
        enabled = self.env['ir.config_parameter'].sudo().get_param(
            'chatroom_ai_agent.enabled', 'False') == 'True'
        if not enabled:
            return 0
        total = 0
        for automation in self.sudo().search([('active', '=', True), ('trigger', 'in', ('daily_review', 'open_conversation'))]):
            try:
                total += automation._run_for_channels(automation._channels_for(automation))
            except Exception:
                self.env.cr.rollback()
        return total

# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class ChatroomOperationsDashboard(models.TransientModel):
    _name = 'chatroom.operations.dashboard'
    _description = 'Panel operativo de Chatroom'

    company_id = fields.Many2one(
        'res.company', string='Empresa', required=True,
        default=lambda self: self.env.company,
    )
    refreshed_at = fields.Datetime(string='Actualizado', readonly=True)
    active_conversations = fields.Integer(string='Conversaciones activas', readonly=True)
    unread_conversations = fields.Integer(string='Conversaciones sin leer', readonly=True)
    sla_attention = fields.Integer(string='SLA por atender', readonly=True)
    abandoned_carts = fields.Integer(string='Carritos abandonados', readonly=True)
    failed_payments = fields.Integer(string='Pagos fallidos', readonly=True)
    pending_payments = fields.Integer(string='Pagos pendientes', readonly=True)
    deliveries_pending = fields.Integer(string='Entregas en curso', readonly=True)
    deliveries_late = fields.Integer(string='Entregas atrasadas', readonly=True)
    ai_pending = fields.Integer(string='Tareas IA pendientes', readonly=True)
    ai_approvals = fields.Integer(string='Aprobaciones IA', readonly=True)
    ai_failed = fields.Integer(string='Tareas IA fallidas', readonly=True)
    stagnant_opportunities = fields.Integer(string='Oportunidades estancadas', readonly=True)
    open_opportunities = fields.Integer(string='Oportunidades abiertas', readonly=True)
    pipeline_value = fields.Monetary(string='Pipeline abierto', currency_field='currency_id', readonly=True)
    stagnant_capital = fields.Monetary(string='Capital atrapado', currency_field='currency_id', readonly=True)
    overdue_activities = fields.Integer(string='Actividades vencidas', readonly=True)
    today_activities = fields.Integer(string='Actividades de hoy', readonly=True)
    ai_requests_today = fields.Integer(string='Solicitudes IA hoy', readonly=True)
    ai_tokens_today = fields.Integer(string='Tokens IA hoy', readonly=True)
    ai_failed_today = fields.Integer(string='Fallos IA hoy', readonly=True)
    ai_config_state = fields.Selection([
        ('disabled', 'Desactivada'), ('incomplete', 'Requiere configuración'),
        ('ready', 'Lista'),
    ], string='Estado de IA', readonly=True)
    whatsapp_state = fields.Selection([
        ('unavailable', 'Sin línea'), ('incomplete', 'Incompleto'), ('ready', 'Configurado'),
    ], string='Estado de WhatsApp', readonly=True)
    payphone_state = fields.Selection([
        ('unavailable', 'No instalado'), ('incomplete', 'No habilitado'), ('ready', 'Disponible'),
    ], string='Estado de PayPhone', readonly=True)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', readonly=True)
    unread_notifications = fields.Integer(string='Alertas sin leer', readonly=True)
    demo_count = fields.Integer(string='Escenarios DEMO QA', readonly=True)
    summary = fields.Char(string='Estado general', readonly=True)
    attention_count = fields.Integer(string='Pendientes de atención', readonly=True)
    priority_level = fields.Selection([
        ('ok', 'Estable'), ('info', 'Informativo'),
        ('warning', 'Requiere seguimiento'), ('critical', 'Atención inmediata'),
    ], string='Prioridad operativa', readonly=True)
    next_action = fields.Char(string='Siguiente acción recomendada', readonly=True)
    setup_next_step = fields.Char(string='Siguiente paso de configuración', readonly=True)

    @api.model
    def action_open_dashboard(self):
        record = self.create({})
        record._refresh_metrics()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Panel operativo'),
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': record.id,
            'target': 'current',
        }

    def _company_domain(self, model_name, domain):
        if model_name in self.env and 'company_id' in self.env[model_name]._fields:
            return list(domain) + [('company_id', '=', self.env.company.id)]
        return domain

    def _count(self, model_name, domain):
        if model_name not in self.env:
            return 0
        return self.env[model_name].sudo().search_count(
            self._company_domain(model_name, domain))

    def _sla_channel_ids(self):
        Channel = self.env['chatroom.channel'].sudo()
        channels = Channel.search(self._company_domain(
            'chatroom.channel', [('state', 'in', ('open', 'pending'))]))
        return channels.filtered(
            lambda channel: channel.first_response_sla_state in ('yellow', 'red')
        ).ids

    def _refresh_metrics(self):
        for record in self:
            record.company_id = self.env.company
            record.refreshed_at = fields.Datetime.now()
            record.active_conversations = self._count('chatroom.channel', [('state', 'in', ('open', 'pending'))])
            record.unread_conversations = self._count('chatroom.channel', [
                ('state', 'in', ('open', 'pending')), ('unread_count', '>', 0),
            ])
            record.sla_attention = len(record._sla_channel_ids())
            record.abandoned_carts = self._count('chatroom.channel', [
                ('state', 'in', ('open', 'pending')),
                ('cart_line_ids', '!=', False),
                ('ai_sales_cart_reminder_count', '>', 0),
            ]) if 'ai_sales_cart_reminder_count' in self.env['chatroom.channel']._fields else 0
            record.failed_payments = self._count('chatroom.payment.link', [('state', '=', 'error')])
            record.pending_payments = self._count('chatroom.payment.link', [('state', 'in', ('generated', 'sent'))])
            record.deliveries_pending = self._count('stock.picking', [
                ('state', 'in', ('waiting', 'confirmed', 'assigned')),
                ('picking_type_code', '=', 'outgoing'),
            ])
            record.deliveries_late = self._count('stock.picking', [
                ('has_deadline_issue', '=', True),
                ('state', 'not in', ('done', 'cancel')),
            ])
            record.ai_pending = self._count('chatroom.ai.task', [('state', 'in', ('awaiting_approval', 'planned', 'running'))])
            record.ai_approvals = self._count('chatroom.ai.task', [('state', '=', 'awaiting_approval')])
            record.ai_failed = self._count('chatroom.ai.task', [('state', '=', 'failed')])
            record.stagnant_opportunities = self._count('crm.lead', [
                ('type', '=', 'opportunity'), ('active', '=', True),
                ('stage_id.is_won', '=', False),
                ('stagnation_score', 'in', ('warning', 'critical', 'stagnant', 'dead')),
            ]) if 'crm.lead' in self.env and 'stagnation_score' in self.env['crm.lead']._fields else 0
            if 'crm.lead' in self.env:
                open_leads = self.env['crm.lead'].sudo().search(self._company_domain('crm.lead', [
                    ('type', '=', 'opportunity'), ('active', '=', True),
                    ('stage_id.is_won', '=', False), ('probability', '<', 100),
                ]))
                record.open_opportunities = len(open_leads)
                record.pipeline_value = sum(open_leads.mapped('expected_revenue'))
                record.stagnant_capital = sum(open_leads.filtered(
                    lambda lead: lead.stagnation_score in ('warning', 'critical', 'stagnant', 'dead')
                ).mapped('estimated_capital_trapped')) if 'stagnation_score' in self.env['crm.lead']._fields else 0.0
            else:
                record.open_opportunities = record.pipeline_value = record.stagnant_capital = 0.0
            today = fields.Date.context_today(record)
            record.overdue_activities = self._count('mail.activity', [
                ('date_deadline', '<', today), ('date_done', '=', False),
            ])
            record.today_activities = self._count('mail.activity', [
                ('date_deadline', '=', today), ('date_done', '=', False),
            ])
            usage_start = fields.Datetime.to_string(fields.Datetime.start_of(fields.Datetime.now(), 'day'))
            usage_end = fields.Datetime.to_string(fields.Datetime.end_of(fields.Datetime.now(), 'day'))
            usage_domain = [('request_date', '>=', usage_start), ('request_date', '<=', usage_end)]
            record.ai_requests_today = self._count('chatroom.ai.usage.event', usage_domain)
            usage = self.env['chatroom.ai.usage.event'].sudo().search(
                self._company_domain('chatroom.ai.usage.event', usage_domain)) if 'chatroom.ai.usage.event' in self.env else False
            record.ai_tokens_today = sum(usage.mapped('total_tokens')) if usage else 0
            record.ai_failed_today = len(usage.filtered(lambda event: not event.success)) if usage else 0
            icp = self.env['ir.config_parameter'].sudo()
            ai_enabled = icp.get_param('chatroom_whatsapp.ai_enabled', 'False') == 'True'
            has_credentials = bool(icp.get_param('chatroom_whatsapp.ai_provider_url') and icp.get_param('chatroom_whatsapp.ai_api_key'))
            record.ai_config_state = 'ready' if ai_enabled and has_credentials else 'incomplete' if ai_enabled else 'disabled'
            if 'chatroom.whatsapp.number' in self.env:
                lines = self.env['chatroom.whatsapp.number'].sudo().search([('active', '=', True)])
                general_token = icp.get_param('chatroom_whatsapp.access_token')
                record.whatsapp_state = (
                    'ready' if any(line.phone_number_id and (line.access_token or general_token) for line in lines)
                    else 'incomplete' if lines else 'unavailable'
                )
            else:
                record.whatsapp_state = 'unavailable'
            if 'payment.provider' in self.env:
                payphone = self.env['payment.provider'].sudo().search([('code', '=', 'payphone')])
                record.payphone_state = (
                    'ready' if payphone.filtered(lambda provider: provider.state in ('enabled', 'test'))
                    else 'incomplete' if payphone else 'unavailable'
                )
            else:
                record.payphone_state = 'unavailable'
            record.unread_notifications = self._count('chatroom.notification', [('state', '=', 'unread')])
            record.demo_count = self._count('res.partner', [('name', 'like', 'DEMO QA%')])
            record.attention_count = (
                record.failed_payments + record.ai_failed + record.sla_attention
                + record.overdue_activities + record.deliveries_late
                + record.stagnant_opportunities + record.unread_conversations
            )
            if record.failed_payments:
                record.priority_level = 'critical'
                record.next_action = _('Revisar pagos fallidos')
            elif record.ai_failed:
                record.priority_level = 'critical'
                record.next_action = _('Revisar tareas IA fallidas')
            elif record.sla_attention:
                record.priority_level = 'critical'
                record.next_action = _('Atender conversaciones fuera de SLA')
            elif record.overdue_activities:
                record.priority_level = 'warning'
                record.next_action = _('Completar actividades vencidas')
            elif record.stagnant_opportunities:
                record.priority_level = 'warning'
                record.next_action = _('Revisar oportunidades estancadas')
            elif record.deliveries_late:
                record.priority_level = 'warning'
                record.next_action = _('Revisar entregas atrasadas')
            elif record.unread_conversations:
                record.priority_level = 'warning'
                record.next_action = _('Atender conversaciones sin leer')
            elif record.pending_payments:
                record.priority_level = 'info'
                record.next_action = _('Dar seguimiento a pagos pendientes')
            else:
                record.priority_level = 'ok'
                record.next_action = _('No hay incidencias prioritarias')
            if record.whatsapp_state != 'ready':
                record.setup_next_step = _('Completar la configuración de WhatsApp')
            elif record.ai_config_state == 'incomplete':
                record.setup_next_step = _('Completar las credenciales del proveedor IA')
            elif record.payphone_state == 'incomplete':
                record.setup_next_step = _('Habilitar el proveedor PayPhone')
            else:
                record.setup_next_step = _('Integraciones listas para operar')
            critical = record.failed_payments + record.ai_failed + record.sla_attention
            record.summary = _('Revisión requerida: %s incidencia(s).') % critical if critical else _('Operación estable.')

    def action_refresh(self):
        self.ensure_one()
        self._refresh_metrics()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_collect_metrics(self):
        self.env['chatroom.operations.metric'].collect_for_date()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Métricas actualizadas'),
                'message': _('El resumen comercial diario quedó actualizado.'),
                'type': 'success',
                'sticky': False,
            },
        }

    def _open(self, model, title, domain):
        return {
            'type': 'ir.actions.act_window', 'name': title, 'res_model': model,
            'view_mode': 'list,form', 'views': [(False, 'list'), (False, 'form')],
            'domain': self._company_domain(model, domain), 'target': 'new',
        }

    def action_open_failed_payments(self):
        return self._open('chatroom.payment.link', _('Pagos fallidos'), [('state', '=', 'error')])

    def action_open_priority(self):
        self.ensure_one()
        if self.failed_payments:
            return self.action_open_failed_payments()
        if self.ai_failed:
            return self.action_open_ai_failed()
        if self.sla_attention:
            return self.action_open_sla()
        if self.overdue_activities:
            return self.action_open_overdue_activities()
        if self.stagnant_opportunities:
            return self.action_open_stagnant_opportunities()
        if self.deliveries_late:
            return self.action_open_late_deliveries()
        if self.unread_conversations:
            return self.action_open_unread_conversations()
        if self.pending_payments:
            return self.action_open_pending_payments()
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'title': _('Operación estable'),
                'message': _('No hay pendientes prioritarios en este momento.'),
                'type': 'success', 'sticky': False,
            },
        }

    def action_open_setup(self):
        self.ensure_one()
        if self.whatsapp_state != 'ready':
            return self.env.ref('chatroom_whatsapp.action_chatroom_onboarding_wizard').read()[0]
        if self.ai_config_state == 'incomplete':
            return self.env.ref('base_setup.action_general_configuration').read()[0]
        if self.payphone_state == 'incomplete':
            return self._open('payment.provider', _('Configurar PayPhone'), [('code', '=', 'payphone')])
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'title': _('Integraciones listas'),
                'message': _('WhatsApp, IA y PayPhone están listos para operar.'),
                'type': 'success', 'sticky': False,
            },
        }

    def action_open_pending_payments(self):
        return self._open('chatroom.payment.link', _('Pagos pendientes'), [('state', 'in', ('generated', 'sent'))])

    def action_open_ai_failed(self):
        return self._open('chatroom.ai.task', _('Tareas IA fallidas'), [('state', '=', 'failed')])

    def action_open_ai_pending(self):
        return self._open('chatroom.ai.task', _('Tareas IA pendientes'), [('state', 'in', ('awaiting_approval', 'planned', 'running'))])

    def action_open_ai_approvals(self):
        return self._open('chatroom.ai.task', _('Aprobaciones IA'), [('state', '=', 'awaiting_approval')])

    def action_open_conversations(self):
        return self._open('chatroom.channel', _('Conversaciones activas'), [('state', 'in', ('open', 'pending'))])

    def action_open_unread_conversations(self):
        return self._open('chatroom.channel', _('Conversaciones sin leer'), [
            ('state', 'in', ('open', 'pending')), ('unread_count', '>', 0),
        ])

    def action_open_abandoned_carts(self):
        return self._open('chatroom.channel', _('Carritos abandonados'), [
            ('state', 'in', ('open', 'pending')), ('cart_line_ids', '!=', False),
            ('ai_sales_cart_reminder_count', '>', 0),
        ])

    def action_open_stagnant_opportunities(self):
        return self._open('crm.lead', _('Oportunidades estancadas'), [
            ('type', '=', 'opportunity'), ('active', '=', True),
            ('stage_id.is_won', '=', False),
            ('stagnation_score', 'in', ('warning', 'critical', 'stagnant', 'dead')),
        ])

    def action_open_open_opportunities(self):
        return self._open('crm.lead', _('Oportunidades abiertas'), [
            ('type', '=', 'opportunity'), ('active', '=', True),
            ('stage_id.is_won', '=', False), ('probability', '<', 100),
        ])

    def action_open_overdue_activities(self):
        return self._open('mail.activity', _('Actividades vencidas'), [
            ('date_deadline', '<', fields.Date.context_today(self)), ('date_done', '=', False),
        ])

    def action_open_today_activities(self):
        return self._open('mail.activity', _('Actividades de hoy'), [
            ('date_deadline', '=', fields.Date.context_today(self)), ('date_done', '=', False),
        ])

    def action_open_ai_usage_today(self):
        return self._open('chatroom.ai.usage.event', _('Consumo IA de hoy'), [
            ('request_date', '>=', fields.Datetime.to_string(fields.Datetime.start_of(fields.Datetime.now(), 'day'))),
            ('request_date', '<=', fields.Datetime.to_string(fields.Datetime.end_of(fields.Datetime.now(), 'day'))),
        ])

    def action_open_ai_errors_today(self):
        return self._open('chatroom.ai.usage.event', _('Fallos IA de hoy'), [
            ('request_date', '>=', fields.Datetime.to_string(fields.Datetime.start_of(fields.Datetime.now(), 'day'))),
            ('request_date', '<=', fields.Datetime.to_string(fields.Datetime.end_of(fields.Datetime.now(), 'day'))),
            ('success', '=', False),
        ])

    def action_open_late_deliveries(self):
        return self._open('stock.picking', _('Entregas atrasadas'), [
            ('has_deadline_issue', '=', True), ('state', 'not in', ('done', 'cancel')),
        ])

    def action_open_demos(self):
        return self._open('res.partner', _('Contactos demo'), [('name', 'like', 'DEMO QA%')])

    def action_open_sla(self):
        ids = self._sla_channel_ids()
        return self._open('chatroom.channel', _('Conversaciones con SLA'), [
            ('id', 'in', ids or [0]),
        ])

    def action_open_deliveries(self):
        return self._open('stock.picking', _('Entregas en curso'), [
            ('state', 'in', ('waiting', 'confirmed', 'assigned')), ('picking_type_code', '=', 'outgoing'),
        ])

    def action_open_notifications(self):
        return self._open('chatroom.notification', _('Alertas operativas'), [('state', '!=', 'done')])

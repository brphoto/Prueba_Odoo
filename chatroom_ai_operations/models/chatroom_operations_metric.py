# -*- coding: utf-8 -*-
from datetime import datetime, time, timedelta

from odoo import api, fields, models


class ChatroomOperationsMetric(models.Model):
    _name = 'chatroom.operations.metric'
    _description = 'Indicadores comerciales diarios de Chatroom'
    _order = 'date desc, id desc'
    _sql_constraints = [
        ('date_company_unique', 'unique(date, company_id)',
         'Ya existe un resumen para esta fecha y empresa.'),
    ]

    date = fields.Date(string='Fecha', required=True, index=True,
                       default=fields.Date.context_today)
    company_id = fields.Many2one(
        'res.company', string='Empresa', required=True, index=True,
        default=lambda self: self.env.company)
    refreshed_at = fields.Datetime(string='Actualizado', readonly=True)

    conversation_count = fields.Integer(string='Conversaciones recibidas')
    active_conversations = fields.Integer(string='Conversaciones activas')
    inbound_messages = fields.Integer(string='Mensajes entrantes')
    outbound_messages = fields.Integer(string='Mensajes salientes')
    avg_first_response_minutes = fields.Float(string='Primera respuesta promedio (min)')
    sla_compliance_rate = fields.Float(string='Cumplimiento SLA (%)')
    opportunities_created = fields.Integer(string='Oportunidades creadas')
    quotation_count = fields.Integer(string='Cotizaciones creadas')
    sales_orders = fields.Integer(string='Pedidos creados')
    confirmed_orders = fields.Integer(string='Pedidos confirmados')
    sales_amount = fields.Monetary(string='Ventas')
    invoice_count = fields.Integer(string='Facturas emitidas')
    invoiced_amount = fields.Monetary(string='Facturación')
    new_customers = fields.Integer(string='Clientes nuevos')
    currency_id = fields.Many2one(
        'res.currency', string='Moneda', required=True,
        default=lambda self: self.env.company.currency_id)
    payment_links_sent = fields.Integer(string='Links enviados')
    payment_links_paid = fields.Integer(string='Links pagados')
    pending_payments = fields.Integer(string='Pagos pendientes')
    ai_requests = fields.Integer(string='Solicitudes IA')
    ai_tokens = fields.Integer(string='Tokens IA')
    ai_messages = fields.Integer(string='Mensajes IA enviados')
    ai_escalations = fields.Integer(string='Escalados a humano')
    ai_confirmed_orders = fields.Integer(string='Pedidos confirmados por IA')
    ai_suggestions_helpful = fields.Integer(string='Sugerencias útiles')
    ai_suggestions_edited = fields.Integer(string='Sugerencias editadas')
    ai_resolution_rate = fields.Float(string='Resolución automática (%)')
    conversion_rate = fields.Float(string='Conversión a pedido (%)')

    @api.model
    def _period(self, day):
        day = fields.Date.to_date(day)
        start = datetime.combine(day, time.min)
        end = start + timedelta(days=1)
        return day, fields.Datetime.to_string(start), fields.Datetime.to_string(end)

    @api.model
    def _records(self, model_name, domain):
        if model_name not in self.env:
            return self.env[model_name].browse() if model_name in self.env else False
        model = self.env[model_name].sudo()
        if 'company_id' in model._fields:
            domain = list(domain) + [('company_id', '=', self.env.company.id)]
        return model.search(domain)

    @api.model
    def _count_period(self, model_name, start, end, extra=None):
        records = self._records(model_name, [
            ('create_date', '>=', start), ('create_date', '<', end),
        ] + (extra or []))
        return len(records) if records is not False else 0

    @api.model
    def collect_for_date(self, day=None):
        day, start, end = self._period(day or fields.Date.context_today(self))
        Channel = self.env['chatroom.channel'].sudo()
        channels = self._records('chatroom.channel', [
            ('create_date', '>=', start), ('create_date', '<', end),
        ])
        messages = self._records('chatroom.message', [
            ('create_date', '>=', start), ('create_date', '<', end),
        ])
        responded = channels.filtered(lambda channel: channel.first_response_minutes > 0)
        compliant = responded.filtered(lambda channel: channel.first_response_minutes < 60)
        avg_response = sum(responded.mapped('first_response_minutes')) / len(responded) if responded else 0.0

        orders = self._records('sale.order', [
            ('create_date', '>=', start), ('create_date', '<', end),
        ])
        invoices = self._records('account.move', [
            ('create_date', '>=', start), ('create_date', '<', end),
            ('move_type', '=', 'out_invoice'), ('state', '=', 'posted'),
        ])
        new_customers = self._records('res.partner', [
            ('create_date', '>=', start), ('create_date', '<', end),
            ('customer_rank', '>', 0),
        ])
        payment_links = self._records('chatroom.payment.link', [
            ('create_date', '>=', start), ('create_date', '<', end),
        ])
        usage = self._records('chatroom.ai.usage.event', [
            ('request_date', '>=', start), ('request_date', '<', end),
        ])
        sales_events = self._records('chatroom.ai.sales.event', [
            ('create_date', '>=', start), ('create_date', '<', end),
        ])
        ai_tasks = self._records('chatroom.ai.task', [
            ('create_date', '>=', start), ('create_date', '<', end),
        ])
        suggestions = self._records('chatroom.ai.suggestion', [
            ('create_date', '>=', start), ('create_date', '<', end),
        ])
        inbound = messages.filtered(lambda message: message.direction == 'inbound') if messages is not False else []
        outbound = messages.filtered(lambda message: message.direction == 'outbound') if messages is not False else []
        ai_messages = outbound.filtered(
            lambda message: 'ai_generated' in message._fields and message.ai_generated)
        confirmed = sales_events.filtered(lambda event: event.event == 'order_confirmed') if sales_events is not False else []
        escalated = sales_events.filtered(lambda event: event.event in ('escalated', 'blocked')) if sales_events is not False else []
        request_count = len(usage) if usage is not False else 0
        token_count = sum(usage.mapped('total_tokens')) if usage is not False else 0
        values = {
            'date': day,
            'company_id': self.env.company.id,
            'refreshed_at': fields.Datetime.now(),
            'conversation_count': len(channels) if channels is not False else 0,
            'active_conversations': len(Channel.search([('state', 'in', ('open', 'pending'))])),
            'inbound_messages': len(inbound),
            'outbound_messages': len(outbound),
            'avg_first_response_minutes': round(avg_response, 2),
            'sla_compliance_rate': round(len(compliant) / len(responded) * 100, 2) if responded else 0.0,
            'opportunities_created': self._count_period('crm.lead', start, end),
            'quotation_count': len(orders.filtered(lambda order: order.state in ('draft', 'sent'))) if orders is not False else 0,
            'sales_orders': len(orders) if orders is not False else 0,
            'confirmed_orders': len(orders.filtered(lambda order: order.state in ('sale', 'done'))) if orders is not False else 0,
            'sales_amount': sum(orders.mapped('amount_total')) if orders is not False else 0.0,
            'invoice_count': len(invoices) if invoices is not False else 0,
            'invoiced_amount': sum(invoices.mapped('amount_total')) if invoices is not False else 0.0,
            'new_customers': len(new_customers) if new_customers is not False else 0,
            'currency_id': self.env.company.currency_id.id,
            'payment_links_sent': len(payment_links.filtered(lambda link: link.state in ('sent', 'paid'))) if payment_links is not False else 0,
            'payment_links_paid': len(payment_links.filtered(lambda link: link.state == 'paid')) if payment_links is not False else 0,
            'pending_payments': len(payment_links.filtered(lambda link: link.state in ('generated', 'sent'))) if payment_links is not False else 0,
            'ai_requests': request_count,
            'ai_tokens': token_count,
            'ai_messages': len(ai_messages),
            'ai_escalations': len(escalated),
            'ai_confirmed_orders': len(confirmed),
            'ai_suggestions_helpful': len(suggestions.filtered(lambda suggestion: suggestion.feedback_state == 'helpful')) if suggestions is not False else 0,
            'ai_suggestions_edited': len(suggestions.filtered(lambda suggestion: suggestion.feedback_state == 'edited')) if suggestions is not False else 0,
            'conversion_rate': round(len(orders) / len(channels) * 100, 2) if channels else 0.0,
            'ai_resolution_rate': round(len(confirmed) / (len(confirmed) + len(escalated)) * 100, 2) if confirmed or escalated else 0.0,
        }
        if ai_tasks is not False and 'state' in ai_tasks._fields:
            values['ai_requests'] = max(values['ai_requests'], len(ai_tasks))
        record = self.search([('date', '=', day), ('company_id', '=', self.env.company.id)], limit=1)
        if record:
            record.write(values)
        else:
            record = self.create(values)
        return record

    @api.model
    def _cron_collect_today(self):
        self.collect_for_date()
        return 1

    @api.model
    def action_collect_today(self):
        record = self.collect_for_date()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Métricas actualizadas',
                'message': 'Se actualizó el resumen comercial del %s.' % record.date,
                'type': 'success',
                'sticky': False,
            },
        }

# -*- coding: utf-8 -*-
from datetime import date, datetime

from odoo import _, api, fields, models


class ChatroomTemplateVariable(models.Model):
    _name = 'chatroom.template.variable'
    _description = 'Origen de variable de plantilla WhatsApp'
    _order = 'sequence, id'

    template_id = fields.Many2one(
        'chatroom.template', required=True, ondelete='cascade')
    sequence = fields.Integer(default=1, required=True)
    placeholder = fields.Char(compute='_compute_placeholder', store=True)
    label = fields.Char(string='Descripción', required=True, default='Variable')
    value_source = fields.Selection([
        ('static', 'Texto fijo'),
        ('contact_name', 'Contacto: nombre'),
        ('contact_phone', 'Contacto: teléfono'),
        ('contact_email', 'Contacto: correo'),
        ('conversation_name', 'Conversación: nombre'),
        ('opportunity_name', 'Oportunidad: nombre'),
        ('opportunity_amount', 'Oportunidad: ingreso esperado'),
        ('quotation_name', 'Presupuesto: número'),
        ('quotation_amount', 'Presupuesto: total'),
        ('quotation_validity', 'Presupuesto: fecha de validez'),
        ('quotation_portal_url', 'Presupuesto: enlace del portal'),
        ('invoice_name', 'Factura: número'),
        ('invoice_total', 'Factura: total'),
        ('invoice_residual', 'Factura: saldo pendiente'),
        ('invoice_due_date', 'Factura: vencimiento'),
        ('invoice_portal_url', 'Factura: enlace del portal'),
        ('activity_summary', 'Actividad: resumen'),
        ('activity_date', 'Actividad: fecha'),
        ('assigned_user_name', 'Responsable: nombre'),
        ('company_name', 'Compañía: nombre'),
    ], string='Origen del dato', required=True, default='static')
    static_value = fields.Char(string='Valor fijo')
    format_type = fields.Selection([
        ('text', 'Texto'),
        ('date', 'Fecha'),
        ('datetime', 'Fecha y hora'),
        ('money', 'Moneda'),
        ('number', 'Número'),
    ], string='Formato', default='text', required=True)

    @api.depends('sequence')
    def _compute_placeholder(self):
        for record in self:
            record.placeholder = '{{%s}}' % record.sequence

    def _get_related_record(self, channel):
        source = self.value_source
        if source.startswith('opportunity_'):
            return channel.pinned_lead_id
        if source.startswith('quotation_'):
            return self.env['sale.order'].search(
                [('partner_id', '=', channel.partner_id.id)],
                order='date_order desc, id desc', limit=1)
        if source.startswith('invoice_'):
            return self.env['account.move'].search(
                [('partner_id', '=', channel.partner_id.id),
                 ('move_type', '=', 'out_invoice')],
                order='invoice_date desc, id desc', limit=1)
        if source.startswith('activity_'):
            return channel._get_partner_activities(limit=1)[:1]
        return self.env[self._name]

    def _raw_value(self, channel):
        partner = channel.partner_id
        source = self.value_source
        if source == 'static':
            return self.static_value or ''
        if source == 'contact_name':
            return partner.name or ''
        if source == 'contact_phone':
            # En Odoo 19 el teléfono móvil se guarda en ``phone``.
            return partner.phone or ''
        if source == 'contact_email':
            return partner.email or ''
        if source == 'conversation_name':
            return channel.display_name or ''
        if source == 'assigned_user_name':
            return channel.assigned_user_id.name or ''
        if source == 'company_name':
            return channel.company_id.name or ''
        record = self._get_related_record(channel)
        if not record:
            return ''
        if source in ('quotation_portal_url', 'invoice_portal_url'):
            return record.get_portal_url() if hasattr(record, 'get_portal_url') else ''
        return {
            'opportunity_name': record.name,
            'opportunity_amount': record.expected_revenue,
            'quotation_name': record.name,
            'quotation_amount': record.amount_total,
            'quotation_validity': record.validity_date,
            'invoice_name': record.name or record.ref,
            'invoice_total': record.amount_total,
            'invoice_residual': record.amount_residual,
            'invoice_due_date': record.invoice_date_due,
            'activity_summary': record.summary or record.activity_type_id.name,
            'activity_date': record.date_deadline,
        }.get(source, '') or ''

    def _format_value(self, value, channel):
        if value in (False, None):
            return ''
        if self.format_type == 'money':
            amount = float(value or 0)
            formatted = f'{amount:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
            return f'{channel.company_id.currency_id.symbol} {formatted}'
        if self.format_type == 'number':
            return f'{float(value):g}'
        if isinstance(value, datetime):
            return value.strftime('%d/%m/%Y %H:%M')
        if isinstance(value, date):
            return value.strftime('%d/%m/%Y')
        return str(value)

    def resolve_value(self, channel):
        self.ensure_one()
        return self._format_value(self._raw_value(channel), channel)

    def name_get(self):
        return [(record.id, f'{record.placeholder} - {record.label}') for record in self]

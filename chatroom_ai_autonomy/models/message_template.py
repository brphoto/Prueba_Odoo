# -*- coding: utf-8 -*-
import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ChatroomAiMessageTemplate(models.Model):
    _name = 'chatroom.ai.message.template'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Plantilla personalizada del agente IA'
    _order = 'sequence, name'

    name = fields.Char(string='Nombre de la plantilla', required=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one(
        'res.company', string='Empresa', default=lambda self: self.env.company,
        required=True, index=True)
    trigger = fields.Selection([
        ('birthday', 'Cumpleaños'), ('inactive_customer', 'Cliente inactivo'),
        ('pending_quote', 'Cotización pendiente'), ('payment_due', 'Pago pendiente'),
        ('delivery_update', 'Actualización de entrega'), ('custom', 'Uso manual'),
    ], string='Uso sugerido', default='custom', required=True)
    delay_days = fields.Integer(string='Días de anticipación', default=0)
    requires_approval = fields.Boolean(string='Requiere aprobación humana', default=True)
    body = fields.Text(string='Mensaje', required=True)
    variable_help = fields.Text(
        string='Variables disponibles', readonly=True,
        default=lambda self: _(
            '{{partner_name}} nombre | {{company_name}} empresa | '
            '{{phone}} teléfono | {{email}} correo | {{today}} fecha | '
            '{{rfm_category}} categoría RFM | {{last_purchase}} última compra'))
    preview_partner_id = fields.Many2one('res.partner', string='Cliente de prueba')
    preview_text = fields.Text(string='Vista previa', readonly=True)

    @api.constrains('delay_days')
    def _check_delay(self):
        for record in self:
            if not -365 <= record.delay_days <= 365:
                raise ValidationError(_('La anticipación debe estar entre -365 y 365 días.'))

    def _values_for(self, partner=False, channel=False):
        partner = partner or (channel.partner_id if channel else False)
        company = (channel.company_id if channel else False) or self.company_id or self.env.company
        values = {
            'partner_name': partner.name if partner else '',
            'company_name': company.name or '',
            'phone': partner.phone if partner else '',
            'email': partner.email if partner else '',
            'today': fields.Date.context_today(self).strftime('%d/%m/%Y'),
            'rfm_category': getattr(partner, 'rfm_category', '') if partner else '',
            'last_purchase': getattr(partner, 'commercial_last_sale_date', '') if partner else '',
        }
        return values

    def render(self, partner=False, channel=False):
        self.ensure_one()
        values = self._values_for(partner=partner, channel=channel)
        return re.sub(
            r'\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}',
            lambda match: str(values.get(match.group(1), match.group(0))),
            self.body or '',
        )

    def action_preview(self):
        self.ensure_one()
        self.preview_text = self.render(partner=self.preview_partner_id)
        return True

    def action_clear_preview(self):
        self.write({'preview_text': False})
        return True

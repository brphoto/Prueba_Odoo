# -*- coding: utf-8 -*-
from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class RfmSegmentRule(models.Model):
    _name = 'crm.rfm.segment.rule'
    _description = 'Regla visual de segmento RFM'
    _order = 'sequence, id'

    segment_id = fields.Many2one(
        'crm.rfm.segment', required=True, ondelete='cascade',
        domain=[('definition_type', '=', 'segment')])
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    field_key = fields.Selection([
        ('rfm_score', 'Score RFM'),
        ('rfm_category', 'Categoría RFM'),
        ('rfm_recency_score', 'Score Recencia'),
        ('rfm_frequency_score', 'Score Frecuencia'),
        ('rfm_monetary_score', 'Score Monetario'),
        ('commercial_total_sales', 'Total comprado'),
        ('commercial_invoice_count', 'Cantidad de facturas'),
        ('commercial_avg_ticket', 'Ticket promedio'),
        ('commercial_last_sale_date', 'Fecha de última compra'),
        ('name', 'Nombre del contacto'),
        ('email', 'Correo electrónico'),
        ('phone', 'Teléfono'),
        ('whatsapp_opt_out', 'Baja de WhatsApp'),
    ], string='Campo', required=True, default='rfm_score')
    operator = fields.Selection([
        ('=', 'Es igual a'), ('!=', 'Es diferente de'),
        ('>=', 'Mayor o igual que'), ('<=', 'Menor o igual que'),
        ('>', 'Mayor que'), ('<', 'Menor que'),
        ('contains', 'Contiene'), ('not_contains', 'No contiene'),
    ], string='Operador', required=True, default='>=')
    value = fields.Char(string='Valor', required=True)

    _COMPARISON_OPERATORS = ('=', '!=', '>=', '<=', '>', '<')

    @api.constrains('field_key', 'operator', 'value')
    def _check_value(self):
        numeric_fields = {
            'rfm_score', 'rfm_recency_score', 'rfm_frequency_score', 'rfm_monetary_score',
            'commercial_total_sales',
            'commercial_invoice_count', 'commercial_avg_ticket',
        }
        for rule in self:
            if rule.field_key in numeric_fields and rule.operator not in self._COMPARISON_OPERATORS:
                raise ValidationError(_('Los campos numéricos solo admiten comparaciones.'))
            if rule.field_key == 'commercial_last_sale_date':
                if rule.operator not in self._COMPARISON_OPERATORS:
                    raise ValidationError(_('Los campos de fecha solo admiten comparaciones.'))
                try:
                    fields.Date.from_string(rule.value)
                except (TypeError, ValueError):
                    raise ValidationError(_('La fecha debe tener formato AAAA-MM-DD.'))

    def _raw_value(self, partner):
        self.ensure_one()
        if self.field_key == 'whatsapp_opt_out':
            return 'true' if getattr(partner, 'whatsapp_opt_out', False) else 'false'
        return partner[self.field_key]

    def matches(self, partner):
        self.ensure_one()
        actual = self._raw_value(partner)
        expected = self.value or ''
        if self.field_key in {
            'rfm_score', 'rfm_recency_score', 'rfm_frequency_score', 'rfm_monetary_score',
            'commercial_total_sales',
            'commercial_invoice_count', 'commercial_avg_ticket',
        }:
            try:
                actual = float(actual or 0)
                expected = float(expected)
            except (TypeError, ValueError):
                return False
        elif self.field_key == 'commercial_last_sale_date':
            actual = actual or date.min
            expected = fields.Date.from_string(expected) if expected else date.min
        else:
            actual = str(actual or '').casefold()
            expected = expected.casefold()
        if self.operator == '=':
            return actual == expected
        if self.operator == '!=':
            return actual != expected
        if self.operator == '>=':
            return actual >= expected
        if self.operator == '<=':
            return actual <= expected
        if self.operator == '>':
            return actual > expected
        if self.operator == '<':
            return actual < expected
        if self.operator == 'contains':
            return expected in actual
        if self.operator == 'not_contains':
            return expected not in actual
        return False

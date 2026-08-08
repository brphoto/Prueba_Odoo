# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class RfmCategory(models.Model):
    _name = 'crm.rfm.category'
    _description = 'Categoría RFM configurable'
    _order = 'sequence, score_min desc, name'

    name = fields.Char(string='Nombre', required=True)
    code = fields.Char(string='Código', required=True, index=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    score_min = fields.Integer(string='Score mínimo', required=True, default=0)
    score_max = fields.Integer(string='Score máximo', required=True, default=100)
    color = fields.Integer(string='Color', default=1)
    is_at_risk = fields.Boolean(string='Marcar como riesgo')
    description = fields.Char(string='Descripción')

    _code_unique = models.Constraint('unique(code)', 'El código de la categoría RFM debe ser único.')

    @api.constrains('score_min', 'score_max', 'code')
    def _check_range(self):
        for record in self:
            if not record.code or not record.code.replace('_', '').isalnum():
                raise ValidationError(_('El código solo puede contener letras, números y guion bajo.'))
            if not 0 <= record.score_min <= 100 or not 0 <= record.score_max <= 100:
                raise ValidationError(_('El rango del score debe estar entre 0 y 100.'))
            if record.score_min > record.score_max:
                raise ValidationError(_('El score mínimo no puede superar al máximo.'))

    @api.model
    def get_dashboard_options(self):
        return [{
            'code': record.code, 'label': record.name, 'color': record.color,
            'is_at_risk': record.is_at_risk,
        } for record in self.search([('active', '=', True)], order='sequence, name')]

    @api.model
    def category_for_score(self, score):
        return self.search([
            ('active', '=', True), ('score_min', '<=', score), ('score_max', '>=', score),
        ], order='sequence, id', limit=1)

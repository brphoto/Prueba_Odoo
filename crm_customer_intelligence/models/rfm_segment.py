# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class RfmSegment(models.Model):
    _name = 'crm.rfm.segment'
    _description = 'Segmento RFM guardado'
    _order = 'sequence, name'

    name = fields.Char(string='Nombre del segmento', required=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    category = fields.Selection([
        ('all', 'Todos'), ('a', 'A - Alto valor'), ('b', 'B - Valor medio'),
        ('c', 'C - Bajo valor'), ('none', 'Sin historial'),
    ], string='Categoría RFM', default='all', required=True)
    category_id = fields.Many2one('crm.rfm.category', string='Categoría configurable')
    score_min = fields.Integer(string='Score mínimo')
    score_max = fields.Integer(string='Score máximo')
    max_days_since_sale = fields.Integer(string='Máximo días desde última venta')
    description = fields.Char(string='Descripción')

    # TambiÃ©n conserva el selector simple, pero lo alimenta con el catÃ¡logo
    # configurable. category_id permite seleccionar el registro directamente.
    category = fields.Selection(
        selection='_selection_rfm_category_filter', string='CategorÃ­a RFM',
        default='all', required=True)

    @api.model
    def _selection_rfm_category_filter(self):
        options = [('all', 'Todos')]
        try:
            options += self.env['res.partner']._selection_rfm_category()
        except Exception:
            options += [
                ('a', 'A - Alto valor'), ('b', 'B - Valor medio'),
                ('c', 'C - Bajo valor'), ('none', 'Sin historial'),
            ]
        return options

    @api.constrains('score_min', 'score_max')
    def _check_score(self):
        for record in self:
            if not 0 <= record.score_min <= 100 or not 0 <= record.score_max <= 100:
                raise ValidationError(_('El score debe estar entre 0 y 100.'))
            if record.score_min and record.score_max and record.score_min > record.score_max:
                raise ValidationError(_('El score mínimo no puede superar al máximo.'))

    def get_domain(self):
        self.ensure_one()
        domain = []
        if self.category != 'all':
            domain.append(('rfm_category', '=', self.category))
        if self.category_id:
            domain = [item for item in domain if item[0] != 'rfm_category']
            domain.append(('rfm_category', '=', self.category_id.code))
        if self.score_min:
            domain.append(('rfm_score', '>=', self.score_min))
        if self.score_max:
            domain.append(('rfm_score', '<=', self.score_max))
        return domain

    def action_open_contacts(self):
        self.ensure_one()
        domain = self.get_domain()
        if self.max_days_since_sale:
            cutoff = fields.Date.subtract(fields.Date.context_today(self), days=self.max_days_since_sale)
            partners = self.env['res.partner'].search(domain).filtered(
                lambda partner: partner.commercial_last_sale_date and
                partner.commercial_last_sale_date >= cutoff)
            domain = [('id', 'in', partners.ids)]
        return {
            'type': 'ir.actions.act_window', 'name': self.name,
            'res_model': 'res.partner', 'view_mode': 'list,form',
            'domain': domain, 'target': 'current',
        }

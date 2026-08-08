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

    rule_logic = fields.Selection([
        ('all', 'Cumplir todas las reglas'), ('any', 'Cumplir al menos una regla'),
    ], string='LÃ³gica de reglas', default='all', required=True)
    rule_ids = fields.One2many(
        'crm.rfm.segment.rule', 'segment_id', string='Reglas visuales', copy=True)
    action_ids = fields.One2many(
        'crm.rfm.segment.action', 'segment_id', string='Acciones automÃ¡ticas', copy=True)
    preview_count = fields.Integer(compute='_compute_preview_count', string='Contactos coincidentes')

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

    def get_matching_partners(self):
        self.ensure_one()
        partners = self.env['res.partner'].search(self.get_domain())
        rules = self.rule_ids.filtered('active')
        if rules:
            if self.rule_logic == 'any':
                partners = partners.filtered(lambda partner: any(rule.matches(partner) for rule in rules))
            else:
                partners = partners.filtered(lambda partner: all(rule.matches(partner) for rule in rules))
        if self.max_days_since_sale:
            cutoff = fields.Date.subtract(fields.Date.context_today(self), days=self.max_days_since_sale)
            partners = partners.filtered(
                lambda partner: partner.commercial_last_sale_date and
                partner.commercial_last_sale_date >= cutoff)
        return partners

    @api.depends('category', 'category_id', 'score_min', 'score_max',
                 'max_days_since_sale', 'rule_logic', 'rule_ids.active',
                 'rule_ids.field_key', 'rule_ids.operator', 'rule_ids.value')
    def _compute_preview_count(self):
        for record in self:
            record.preview_count = len(record.get_matching_partners())

    def action_preview_contacts(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _('Contactos: %s') % self.name,
            'res_model': 'res.partner', 'view_mode': 'list,form',
            'domain': [('id', 'in', self.get_matching_partners().ids)], 'target': 'current',
        }

    def action_apply_automations(self):
        actions = self.mapped('action_ids').filtered('active')
        return actions.action_apply()

    @api.model
    def _cron_apply_segment_actions(self):
        for segment in self.search([('active', '=', True)]):
            segment.action_apply_automations()

    def action_open_contacts(self):
        self.ensure_one()
        domain = [('id', 'in', self.get_matching_partners().ids)]
        return {
            'type': 'ir.actions.act_window', 'name': self.name,
            'res_model': 'res.partner', 'view_mode': 'list,form',
            'domain': domain, 'target': 'current',
        }

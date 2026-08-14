# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class RfmSegment(models.Model):
    _name = 'crm.rfm.segment'
    _description = 'Definición RFM (categoría o segmento)'
    _order = 'definition_type, sequence, score_min desc, name'

    name = fields.Char(string='Nombre del segmento', required=True)
    definition_type = fields.Selection([
        ('category', 'Categoría de clasificación'),
        ('segment', 'Segmento de clientes'),
    ], string='Tipo de definición', required=True, default='segment', index=True,
        help='Las categorías clasifican el score RFM. Los segmentos construyen audiencias con reglas y acciones.')
    code = fields.Char(string='Código', index=True, copy=False,
        help='Código técnico usado por la clasificación RFM. Solo aplica a categorías.')
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    color = fields.Integer(string='Color', default=1)
    icon = fields.Char(
        string='Ícono', default='fa-users',
        help="Clase de ícono FontAwesome para la tarjeta del dashboard, "
             "por ejemplo fa-trophy, fa-user-circle, fa-usd, fa-handshake-o, "
             "fa-user-plus, fa-street-view, fa-bed. Ver "
             "fontawesome.com/v4/icons para más opciones.")
    category_id = fields.Many2one(
        'crm.rfm.segment', string='Categoría RFM', index=True,
        domain=[('definition_type', '=', 'category')],
        help='Categoría RFM base del segmento. Vacío significa todas las categorías.')
    use_score_filter = fields.Boolean(
        string='Filtrar por score', default=False,
        help="score_min y score_max son enteros normales: 0 es un valor válido, no "
             "'sin filtro'. Sin este interruptor no hay forma de distinguir un score "
             "mínimo/máximo de 0 configurado a propósito de los campos simplemente sin "
             "tocar, así que el filtro de score solo se aplica cuando está activado.")
    max_days_since_sale = fields.Integer(string='Máximo días desde última venta')
    description = fields.Char(string='Descripción')

    # Campos de clasificación. En el mismo modelo que los segmentos para
    # que exista un único catálogo RFM y no dos definiciones paralelas.
    score_min = fields.Integer(string='Score mínimo', default=0)
    score_max = fields.Integer(string='Score máximo', default=100)
    is_at_risk = fields.Boolean(string='Marcar como riesgo')

    rule_logic = fields.Selection([
        ('all', 'Cumplir todas las reglas'), ('any', 'Cumplir al menos una regla'),
    ], string='Lógica de reglas', default='all', required=True)
    rule_ids = fields.One2many(
        'crm.rfm.segment.rule', 'segment_id', string='Reglas visuales', copy=True)
    action_ids = fields.One2many(
        'crm.rfm.segment.action', 'segment_id', string='Acciones automáticas', copy=True)
    preview_count = fields.Integer(compute='_compute_preview_count', string='Contactos coincidentes')
    preview_count_pct = fields.Float(
        compute='_compute_preview_count', string='% Clientes',
        help="Porcentaje de contactos coincidentes sobre el total de la cartera con clasificación RFM.")
    revenue_pct = fields.Float(
        compute='_compute_preview_count', string='% Ingresos',
        help="Porcentaje del monto RFM acumulado de los contactos coincidentes sobre el total de la cartera.")
    lead_count = fields.Integer(compute='_compute_related_counts', string='Leads abiertos')
    quotation_count = fields.Integer(compute='_compute_related_counts', string='Cotizaciones')
    sale_count = fields.Integer(compute='_compute_related_counts', string='Ventas')
    sale_count_pct = fields.Float(
        compute='_compute_related_counts', string='% Órdenes',
        help="Porcentaje de las órdenes de venta confirmadas de este segmento "
             "sobre el total de la cartera analizada.")
    mailing_count = fields.Integer(compute='_compute_related_counts', string='Campañas de correo')
    calc_last_run_text = fields.Char(compute='_compute_calc_info', string='Último cálculo')

    _code_unique = models.Constraint(
        "unique(code)",
        'El código de la definición RFM debe ser único.')

    @api.constrains('definition_type', 'code', 'score_min', 'score_max')
    def _check_score(self):
        for record in self:
            if record.definition_type == 'category' and not record.code:
                raise ValidationError(_('Las categorías RFM deben tener un código.'))
            if not 0 <= record.score_min <= 100 or not 0 <= record.score_max <= 100:
                raise ValidationError(_('El score debe estar entre 0 y 100.'))
            if record.score_min > record.score_max:
                raise ValidationError(_('El score mínimo no puede superar al máximo.'))
            if record.category_id and record.category_id.definition_type != 'category':
                raise ValidationError(_('Un segmento solo puede enlazar una categoría RFM.'))
            if record.definition_type == 'segment' and record.category_id == record:
                raise ValidationError(_('Un segmento no puede ser su propia categoría.'))

    @api.constrains('definition_type', 'code', 'category_id')
    def _check_definition_shape(self):
        """Keep the two meanings separate inside the unified catalog."""
        for record in self:
            if record.definition_type == 'category' and record.category_id:
                raise ValidationError(_(
                    'Una categoría de clasificación no puede depender de otra categoría.'))
            if record.definition_type == 'segment' and record.code:
                raise ValidationError(_(
                    'El código técnico solo aplica a categorías de clasificación.'))

    @api.model
    def _category_options(self, include_all=True):
        options = [('all', 'Todas')] if include_all else []
        options += [
            (record.code, record.name)
            for record in self.search(
                [('definition_type', '=', 'category'), ('active', '=', True)],
                order='sequence, id')
        ]
        return options

    @api.model
    def get_dashboard_options(self):
        return [{
            'code': record.code, 'label': record.name, 'color': record.color,
            'is_at_risk': record.is_at_risk,
        } for record in self.search([
            ('definition_type', '=', 'category'), ('active', '=', True),
        ], order='sequence, name')]

    @api.model
    def category_for_score(self, score):
        return self.search([
            ('definition_type', '=', 'category'), ('active', '=', True),
            ('score_min', '<=', score), ('score_max', '>=', score),
        ], order='sequence, id', limit=1)

    def get_domain(self):
        self.ensure_one()
        domain = []
        if self.category_id:
            domain.append(('rfm_category', '=', self.category_id.code))
        if self.use_score_filter:
            domain.append(('rfm_score', '>=', self.score_min))
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
                lambda partner: (partner.rfm_last_purchase_date or partner.commercial_last_sale_date) and
                (partner.rfm_last_purchase_date or partner.commercial_last_sale_date) >= cutoff)
        return partners

    @api.depends('category_id', 'use_score_filter', 'score_min', 'score_max',
                 'max_days_since_sale', 'rule_logic', 'rule_ids.active',
                 'rule_ids.field_key', 'rule_ids.operator', 'rule_ids.value')
    def _compute_preview_count(self):
        # Los porcentajes se calculan sobre el total de contactos con
        # clasificación RFM vigente (rfm_score o rfm_category != 'none'),
        # no sobre el total de contactos de Odoo.
        total_partners = self.env['res.partner'].search_count([('rfm_category', '!=', 'none')])
        total_monetary_all = sum(self.env['res.partner'].search(
            [('rfm_category', '!=', 'none')]).mapped('rfm_monetary_value'))
        for record in self:
            partners = record.get_matching_partners()
            record.preview_count = len(partners)
            record.preview_count_pct = (
                len(partners) / total_partners * 100 if total_partners else 0.0
            )
            record.revenue_pct = (
                sum(partners.mapped('rfm_monetary_value')) / total_monetary_all * 100
                if total_monetary_all else 0.0
            )

    def _compute_related_counts(self):
        total_sales = self.env['sale.order'].search_count([('state', '=', 'sale')])
        for record in self:
            partners = record.get_matching_partners()
            record.lead_count = self.env['crm.lead'].search_count([
                ('partner_id', 'in', partners.ids), ('type', '=', 'opportunity'),
                ('active', '=', True),
            ]) if partners else 0
            record.quotation_count = self.env['sale.order'].search_count([
                ('partner_id', 'in', partners.ids), ('state', 'in', ('draft', 'sent')),
            ]) if partners else 0
            record.sale_count = self.env['sale.order'].search_count([
                ('partner_id', 'in', partners.ids), ('state', '=', 'sale'),
            ]) if partners else 0
            record.sale_count_pct = (
                record.sale_count / total_sales * 100 if total_sales else 0.0
            )
            record.mailing_count = self.env['mailing.mailing'].search_count([
                ('subject', 'ilike', record.name),
            ]) if record.name and 'mailing.mailing' in self.env else 0

    def _compute_calc_info(self):
        computed_dates = self.env['res.partner'].search(
            [('rfm_last_computed_at', '!=', False)]).mapped('rfm_last_computed_at')
        last_run = max(computed_dates) if computed_dates else False
        for record in self:
            record.calc_last_run_text = (
                'Último cálculo: %s' % last_run if last_run else 'Aún no se ha calculado.'
            )

    def action_preview_contacts(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _('Contactos: %s') % self.name,
            'res_model': 'res.partner', 'view_mode': 'kanban,list,form',
            'domain': [('id', 'in', self.get_matching_partners().ids)], 'target': 'current',
        }

    def action_open_segment_leads(self):
        self.ensure_one()
        action = self.env['ir.actions.actions']._for_xml_id('crm.crm_lead_opportunities')
        action['domain'] = [
            ('partner_id', 'in', self.get_matching_partners().ids), ('type', '=', 'opportunity'),
        ]
        return action

    def action_open_segment_quotations(self):
        self.ensure_one()
        action = self.env['ir.actions.actions']._for_xml_id('sale.action_quotations_with_onboarding')
        action['domain'] = [
            ('partner_id', 'in', self.get_matching_partners().ids), ('state', 'in', ('draft', 'sent')),
        ]
        return action

    def action_open_segment_sales(self):
        self.ensure_one()
        action = self.env['ir.actions.actions']._for_xml_id('sale.action_orders')
        action['domain'] = [
            ('partner_id', 'in', self.get_matching_partners().ids), ('state', '=', 'sale'),
        ]
        return action

    def action_open_segment_mailings(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _('Campañas: %s') % self.name,
            'res_model': 'mailing.mailing', 'view_mode': 'list,form',
            'domain': [('subject', 'ilike', self.name)],
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

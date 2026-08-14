# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class RfmReactivationRule(models.Model):
    _name = 'rfm.reactivation.rule'
    _description = 'Regla de reactivación RFM'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    category_code = fields.Selection(
        selection='_selection_rfm_category', string='Categoría RFM',
        required=True, default='a')
    days_allowed = fields.Integer(string='Días sin comprar', required=True, default=30)
    user_id = fields.Many2one('res.users', string='Asignar a asesor')
    team_id = fields.Many2one('crm.team', string='Equipo de ventas')
    lead_description = fields.Text(default='Contactar con oferta especial.')
    last_run = fields.Datetime(readonly=True, copy=False)

    @api.constrains('days_allowed')
    def _check_days_allowed(self):
        for rule in self:
            if rule.days_allowed < 1:
                raise ValidationError(_('Los días sin comprar deben ser mayores que cero.'))

    @api.model
    def _selection_rfm_category(self):
        """Usa el catálogo unificado de categorías, no una lista fija A/B/C."""
        categories = self.env['crm.rfm.segment'].search(
            [('definition_type', '=', 'category'), ('active', '=', True)],
            order='sequence, id')
        return [(category.code, category.name) for category in categories]

    @api.model
    def _cron_process_reactivation(self):
        today = fields.Date.context_today(self)
        Partner = self.env['res.partner']
        Lead = self.env['crm.lead']
        created = 0
        for rule in self.search([('active', '=', True)]):
            cutoff = today - timedelta(days=max(1, rule.days_allowed))
            # RFM ya consolida facturas, POS/pedidos y los historicos
            # importados. Usar sus campos indexados evita cargar todos los
            # contactos y hacer un search_count por cada uno.
            partners = Partner.search([
                ('rfm_category', '=', rule.category_code),
                ('rfm_last_purchase_date', '<', cutoff),
            ])
            open_lead_partner_ids = set(Lead.search([
                ('partner_id', 'in', partners.ids), ('active', '=', True),
                ('probability', '<', 100),
            ]).mapped('partner_id').ids)
            lead_values = []
            for partner in partners:
                if partner.id in open_lead_partner_ids:
                    continue
                assigned = rule.user_id
                if not assigned and 'user_id' in partner._fields:
                    assigned = partner.user_id
                lead_values.append({
                    'name': _('Reactivación RFM - %s') % partner.name,
                    'partner_id': partner.id,
                    'user_id': assigned.id if assigned else False,
                    'team_id': rule.team_id.id if rule.team_id else False,
                    'description': _(
                        'Cliente categoría %(category)s sin comprar hace %(days)s días. %(description)s'
                    ) % {
                        'category': rule.category_code.upper(),
                        'days': rule.days_allowed,
                        'description': rule.lead_description or '',
                    },
                })
            if lead_values:
                Lead.create(lead_values)
                created += len(lead_values)
            rule.last_run = fields.Datetime.now()
        return created

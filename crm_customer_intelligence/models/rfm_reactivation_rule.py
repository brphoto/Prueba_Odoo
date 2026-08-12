# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, api, fields, models


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

    @api.model
    def _selection_rfm_category(self):
        """Usa el catálogo crm.rfm.category, no una lista fija A/B/C."""
        categories = self.env['crm.rfm.category'].search(
            [('active', '=', True)], order='sequence, id')
        return [(category.code, category.name) for category in categories]

    @api.model
    def _cron_process_reactivation(self):
        today = fields.Date.context_today(self)
        Partner = self.env['res.partner']
        Lead = self.env['crm.lead']
        created = 0
        for rule in self.search([('active', '=', True)]):
            cutoff = today - timedelta(days=max(1, rule.days_allowed))
            partners = Partner.search([]).filtered(lambda partner: (
                partner.rfm_category == rule.category_code
                and partner.commercial_last_sale_date
                and partner.commercial_last_sale_date < cutoff
            ))
            for partner in partners:
                if Lead.search_count([
                    ('partner_id', '=', partner.id), ('active', '=', True),
                    ('probability', '<', 100),
                ]):
                    continue
                assigned = rule.user_id
                if not assigned and 'user_id' in partner._fields:
                    assigned = partner.user_id
                Lead.create({
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
                created += 1
            rule.last_run = fields.Datetime.now()
        return created

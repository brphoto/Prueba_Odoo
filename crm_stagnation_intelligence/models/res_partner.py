# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    intelligence_stagnant_count = fields.Integer(
        string='Oportunidades en riesgo', compute='_compute_pipeline_intelligence')
    intelligence_stagnant_capital = fields.Monetary(
        string='Capital en riesgo', currency_field='currency_id',
        compute='_compute_pipeline_intelligence')
    intelligence_pipeline_health = fields.Selection([
        ('healthy', 'Saludable'),
        ('warning', 'Requiere atención'),
        ('critical', 'Crítico'),
    ], string='Salud del pipeline', compute='_compute_pipeline_intelligence')

    def _compute_pipeline_intelligence(self):
        Lead = self.env['crm.lead']
        for partner in self:
            partner_ids = self.search([('id', 'child_of', partner.id)]).ids
            leads = Lead.search([
                ('partner_id', 'in', partner_ids),
                ('active', '=', True),
                ('type', '=', 'opportunity'),
                ('stage_id.is_won', '=', False),
            ])
            risk_leads = leads.filtered(
                lambda lead: lead.stagnation_score in ('warning', 'critical', 'stagnant', 'dead'))
            partner.intelligence_stagnant_count = len(risk_leads)
            partner.intelligence_stagnant_capital = sum(
                risk_leads.mapped('estimated_capital_trapped'))
            levels = set(risk_leads.mapped('stagnation_score'))
            if levels.intersection({'critical', 'stagnant', 'dead'}):
                partner.intelligence_pipeline_health = 'critical'
            elif 'warning' in levels:
                partner.intelligence_pipeline_health = 'warning'
            else:
                partner.intelligence_pipeline_health = 'healthy'

    def action_open_pipeline_intelligence(self):
        self.ensure_one()
        partner_ids = self.search([('id', 'child_of', self.id)]).ids
        view_refs = [
            ('view_crm_integrated_pipeline_list', 'list'),
            ('view_crm_integrated_pipeline_kanban', 'kanban'),
            ('view_crm_integrated_pipeline_graph', 'graph'),
            ('view_crm_integrated_pipeline_pivot', 'pivot'),
        ]
        views = [
            (self.env.ref('crm_stagnation_intelligence.%s' % xmlid).id, view_mode)
            for xmlid, view_mode in view_refs
        ]
        views.append((False, 'form'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Salud del pipeline'),
            'res_model': 'crm.lead',
            'view_mode': 'list,kanban,graph,pivot,form',
            'views': views,
            'search_view_id': self.env.ref(
                'crm_stagnation_intelligence.view_crm_integrated_pipeline_search').id,
            'domain': [
                ('partner_id', 'in', partner_ids),
                ('active', '=', True),
                ('type', '=', 'opportunity'),
                ('stage_id.is_won', '=', False),
            ],
            'context': {'search_default_group_integrated_stagnation': 1},
        }

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

    RISK_LEVELS = ('warning', 'critical', 'stagnant', 'dead')

    def _descendants_by_ancestor(self):
        """{id del contacto: ids de el mismo y sus hijos}.

        `res.partner` no usa `_parent_store`, asi que no hay `parent_path`
        que consultar: se traen todos los descendientes en UNA busqueda y
        el arbol se recorre en memoria. Antes se hacia un `child_of` por
        contacto, y en la lista de contactos eso eran dos consultas por
        fila solo para pintar el semaforo del pipeline.
        """
        if not self.ids:
            return {}
        descendants = self.search([('id', 'child_of', self.ids)])
        parent_of = {
            record.id: record.parent_id.id for record in descendants
        }
        targets = set(self.ids)
        result = {target: {target} for target in targets}
        for descendant_id in parent_of:
            current = descendant_id
            seen = set()
            while current and current not in seen:
                seen.add(current)
                if current in targets:
                    result[current].add(descendant_id)
                current = parent_of.get(current)
        return result

    def _compute_pipeline_intelligence(self):
        Lead = self.env['crm.lead']
        descendants_by_ancestor = self._descendants_by_ancestor()
        every_descendant = {
            partner_id
            for group in descendants_by_ancestor.values()
            for partner_id in group
        }
        leads_by_partner = {}
        if every_descendant:
            # Una sola busqueda de oportunidades para todo el lote.
            for lead in Lead.search([
                ('partner_id', 'in', list(every_descendant)),
                ('active', '=', True),
                ('type', '=', 'opportunity'),
                ('stage_id.is_won', '=', False),
            ]):
                leads_by_partner.setdefault(lead.partner_id.id, Lead)
                leads_by_partner[lead.partner_id.id] |= lead
        for partner in self:
            leads = Lead
            for partner_id in descendants_by_ancestor.get(partner.id, ()):
                leads |= leads_by_partner.get(partner_id, Lead)
            risk_leads = leads.filtered(
                lambda lead: lead.stagnation_score in self.RISK_LEVELS)
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

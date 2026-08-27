# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class CrmExperienceSnapshot(models.Model):
    _name = 'crm.experience.snapshot'
    _description = 'Resumen NPS y LTV'
    _order = 'snapshot_date desc, id desc'

    snapshot_date = fields.Date(string='Fecha', required=True, default=fields.Date.context_today, index=True)
    response_count = fields.Integer(string='Respuestas NPS')
    promoter_count = fields.Integer(string='Promotores')
    passive_count = fields.Integer(string='Pasivos')
    detractor_count = fields.Integer(string='Detractores')
    nps_value = fields.Float(string='NPS global', digits=(16, 2))
    average_ltv = fields.Monetary(string='LTV promedio', currency_field='currency_id')
    average_rfm = fields.Float(string='RFM promedio', digits=(16, 2))
    vip_risk_count = fields.Integer(string='VIP en riesgo')
    evangelist_count = fields.Integer(string='Evangelistas')
    champions_count = fields.Integer(string='Campeones')
    lost_count = fields.Integer(string='Perdidos')
    currency_id = fields.Many2one('res.currency', required=True, default=lambda self: self.env.company.currency_id)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)

    _date_company_unique = models.Constraint('UNIQUE (snapshot_date, company_id)', 'Solo puede existir un resumen por día y empresa.')

    @api.model
    def _refresh_today(self):
        today = fields.Date.context_today(self)
        Response = self.env['crm.nps.response'].sudo()
        Partner = self.env['res.partner'].sudo()
        total = Response.search_count([])
        promoters = Response.search_count([('category', '=', 'promoter')])
        passive = Response.search_count([('category', '=', 'passive')])
        detractors = Response.search_count([('category', '=', 'detractor')])
        nps = ((promoters - detractors) / total * 100.0) if total else 0.0
        customers = Partner.search([('ltv_value', '>', 0)])
        avg_ltv = sum(customers.mapped('ltv_value')) / len(customers) if customers else 0.0
        rfm_customers = Partner.search([('rfm_score', '>', 0)])
        avg_rfm = sum(rfm_customers.mapped('rfm_score')) / len(rfm_customers) if rfm_customers else 0.0
        values = {
            'response_count': total, 'promoter_count': promoters, 'passive_count': passive,
            'detractor_count': detractors, 'nps_value': nps, 'average_ltv': avg_ltv, 'average_rfm': avg_rfm,
            'vip_risk_count': Partner.search_count([('strategic_segment', '=', 'vip_risk')]),
            'evangelist_count': Partner.search_count([('strategic_segment', '=', 'evangelist')]),
            'champions_count': Partner.search_count([('strategic_segment', '=', 'champions')]),
            'lost_count': Partner.search_count([('strategic_segment', '=', 'lost')]),
        }
        snapshot = self.search([('snapshot_date', '=', today), ('company_id', '=', self.env.company.id)], limit=1)
        if snapshot:
            snapshot.write(values)
        else:
            self.create(dict(values, snapshot_date=today, company_id=self.env.company.id,
                             currency_id=self.env.company.currency_id.id))
        return True

    def action_refresh(self):
        self._refresh_today()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    @api.model
    def cron_refresh(self):
        self.env['res.partner'].action_recompute_experience_metrics()
        self._refresh_today()
        return True

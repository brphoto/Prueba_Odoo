# -*- coding: utf-8 -*-
from odoo import api, fields, models


class CrmRfmSnapshot(models.Model):
    _name = 'crm.rfm.snapshot'
    _description = 'Histórico mensual de clasificación RFM por cliente'
    _order = 'snapshot_date desc, partner_id'

    snapshot_date = fields.Date(required=True, default=fields.Date.context_today, index=True)
    partner_id = fields.Many2one('res.partner', required=True, index=True, ondelete='cascade')
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)
    currency_id = fields.Many2one(related='company_id.currency_id', store=True)

    rfm_score = fields.Integer(string='Score RFM')
    rfm_category = fields.Char(string='Categoría RFM (código)')
    rfm_recency_days = fields.Integer(string='Recencia (días)')
    rfm_frequency = fields.Integer(string='Frecuencia RFM')
    rfm_monetary_value = fields.Monetary(string='Valor monetario RFM')

    _snapshot_unique = models.Constraint(
        'unique(snapshot_date, partner_id, company_id)',
        'Ya existe un histórico RFM para este cliente y fecha.')

    @api.model
    def _cron_snapshot_rfm(self):
        """Guarda una foto mensual de la clasificación RFM vigente de
        cada cliente. Es un cron aparte del de recálculo diario
        (`_cron_compute_rfm_scores`) a propósito: capturar el score todos
        los días generaría un histórico enorme y ruidoso sin aportar
        nada -para "¿en qué segmento estaba este cliente hace 6 meses?"
        alcanza y sobra con una foto por mes, igual que
        `crm.kpi.snapshot`."""
        today = fields.Date.context_today(self)
        # Avoid one existence query per partner during the monthly cron.
        existing = self.search([('snapshot_date', '=', today)])
        existing_by_key = {
            (snapshot.partner_id.id, snapshot.company_id.id): snapshot
            for snapshot in existing
        }
        to_create = []
        for company in self.env['res.company'].search([]):
            partners = self.env['res.partner'].search([
                ('company_id', 'in', (False, company.id)),
                '|', ('rfm_frequency', '>', 0), ('rfm_category', '!=', 'none'),
            ])
            for partner in partners:
                vals = {
                    'rfm_score': partner.rfm_score,
                    'rfm_category': partner.rfm_category,
                    'rfm_recency_days': partner.rfm_recency_days,
                    'rfm_frequency': partner.rfm_frequency,
                    'rfm_monetary_value': partner.rfm_monetary_value,
                }
                snapshot = existing_by_key.get((partner.id, company.id))
                if snapshot:
                    snapshot.write(vals)
                else:
                    to_create.append({
                        'snapshot_date': today, 'partner_id': partner.id,
                        'company_id': company.id, **vals,
                    })
        if to_create:
            self.create(to_create)

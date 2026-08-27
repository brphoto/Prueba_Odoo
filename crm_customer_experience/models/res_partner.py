# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


STRATEGIC_SEGMENTS = [
    ('vip_risk', 'VIP en riesgo'),
    ('evangelist', 'Evangelista'),
    ('champions', 'Campeones'),
    ('lost', 'Perdidos'),
    ('neutral', 'En observación'),
    ('no_data', 'Sin datos suficientes'),
]


class ResPartner(models.Model):
    _inherit = 'res.partner'

    nps_response_ids = fields.One2many('crm.nps.response', 'partner_id', string='Respuestas NPS', readonly=True)
    nps_response_count = fields.Integer(string='Cantidad de respuestas NPS', readonly=True)
    nps_score = fields.Integer(string='Última puntuación NPS', readonly=True)
    nps_category = fields.Selection([
        ('detractor', 'Detractor'), ('passive', 'Pasivo'), ('promoter', 'Promotor'),
    ], string='Última categoría NPS', readonly=True)
    nps_last_response_date = fields.Date(string='Última respuesta NPS', readonly=True)
    ltv_value = fields.Monetary(string='LTV estimado', currency_field='currency_id', readonly=True,
                                help='Ticket promedio × frecuencia anual × vida útil estimada.')
    ltv_average_ticket = fields.Monetary(string='Ticket promedio LTV', currency_field='currency_id', readonly=True)
    ltv_annual_frequency = fields.Float(string='Frecuencia anual LTV', readonly=True, digits=(16, 2))
    ltv_lifetime_years = fields.Float(string='Vida útil (años)', readonly=True, digits=(16, 2))
    ltv_first_sale_date = fields.Date(string='Primera venta', readonly=True)
    ltv_last_sale_date = fields.Date(string='Última venta LTV', readonly=True)
    strategic_segment = fields.Selection(selection=STRATEGIC_SEGMENTS, string='Segmento estratégico', readonly=True,
                                         index=True, help='Cruza RFM y la última categoría NPS.')
    strategic_segment_explanation = fields.Text(string='Explicación del segmento', readonly=True)

    @api.model
    def _experience_expected_lifetime_years(self):
        value = self.env['ir.config_parameter'].sudo().get_param(
            'crm_customer_experience.expected_lifetime_years', '3')
        try:
            return max(float(value), 1.0)
        except (TypeError, ValueError):
            return 3.0

    @api.model
    def _experience_segment(self, partner):
        if not partner.nps_category or not partner.rfm_frequency:
            return 'no_data', _('Faltan compras válidas o una respuesta NPS para segmentar.')
        high_rfm = partner.rfm_category == 'a' or partner.rfm_score >= 70
        low_rfm = partner.rfm_category == 'c' or (0 < partner.rfm_score <= 40)
        if high_rfm and partner.nps_category == 'detractor':
            return 'vip_risk', _('Cliente de alto valor con insatisfacción: requiere retención prioritaria.')
        if low_rfm and partner.nps_category == 'promoter':
            return 'evangelist', _('Cliente promotor: oportunidad de recomendación, upsell o cross-sell.')
        if high_rfm and partner.nps_category == 'promoter':
            return 'champions', _('Cliente de alto valor y promotor: cuidar como cliente VIP.')
        if low_rfm and partner.nps_category == 'detractor':
            return 'lost', _('Bajo valor e insatisfecho: revisar antes de invertir acciones automáticas.')
        return 'neutral', _('Segmento mixto: mantener seguimiento comercial normal.')

    @api.model
    def action_recompute_experience_metrics(self):
        """Recalcula LTV y el cruce RFM/NPS en lote, no durante la navegación."""
        Move = self.env['account.move'].sudo()
        rows = Move._read_group([
            ('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('partner_id', '!=', False),
        ], groupby=['partner_id'], aggregates=['amount_total_signed:sum', '__count', 'invoice_date:min', 'invoice_date:max'])
        data = {}
        for partner, total, count, first_date, last_date in rows:
            if partner:
                data[partner.id] = {'total': total or 0.0, 'count': count or 0, 'first': first_date, 'last': last_date}
        partners = self.sudo().search([('customer_rank', '>', 0)]) | self.sudo().browse(list(data))
        expected_years = self._experience_expected_lifetime_years()
        today = fields.Date.context_today(self)
        for partner in partners:
            sale = data.get(partner.id, {})
            total, count = sale.get('total', 0.0), sale.get('count', 0)
            first = fields.Date.to_date(sale.get('first')) if sale.get('first') else False
            last = fields.Date.to_date(sale.get('last')) if sale.get('last') else False
            historical_years = max(((today - first).days / 365.25), 1.0) if first else 0.0
            annual_frequency = (count / historical_years) if historical_years else 0.0
            average_ticket = (total / count) if count else 0.0
            ltv = average_ticket * annual_frequency * expected_years
            segment, explanation = self._experience_segment(partner)
            partner.write({
                'nps_response_count': len(partner.nps_response_ids),
                'ltv_value': ltv, 'ltv_average_ticket': average_ticket,
                'ltv_annual_frequency': annual_frequency,
                'ltv_lifetime_years': expected_years if count else 0.0,
                'ltv_first_sale_date': first, 'ltv_last_sale_date': last,
                'strategic_segment': segment, 'strategic_segment_explanation': explanation,
            })
        without_sales = partners.filtered(lambda p: p.id not in data)
        if without_sales:
            without_sales.write({'ltv_value': 0.0, 'ltv_average_ticket': 0.0,
                                 'ltv_annual_frequency': 0.0, 'ltv_lifetime_years': 0.0,
                                 'ltv_first_sale_date': False, 'ltv_last_sale_date': False})
        return True

    @api.model
    def _refresh_nps_summary(self, partner_ids):
        partners = self.sudo().browse(partner_ids).exists()
        Response = self.env['crm.nps.response'].sudo()
        for partner in partners:
            latest = Response.search([('partner_id', '=', partner.id)], order='response_date desc, id desc', limit=1)
            segment, explanation = self._experience_segment(partner)
            partner.write({
                'nps_response_count': Response.search_count([('partner_id', '=', partner.id)]),
                'nps_score': latest.score if latest else 0,
                'nps_category': latest.category if latest else False,
                'nps_last_response_date': latest.response_date if latest else False,
                'strategic_segment': segment, 'strategic_segment_explanation': explanation,
            })

    def action_schedule_nps_followup(self):
        self.ensure_one()
        activity_type = self.env['mail.activity.type'].search([], order='sequence, id', limit=1)
        if not activity_type:
            return True
        self.env['mail.activity'].create({
            'activity_type_id': activity_type.id, 'summary': _('Recuperar cliente VIP en riesgo'),
            'note': self.strategic_segment_explanation or _('Revisar satisfacción y contactar al cliente.'),
            'date_deadline': fields.Date.add(fields.Date.context_today(self), days=1),
            'user_id': self.env.user.id, 'res_model_id': self.env['ir.model']._get_id('res.partner'), 'res_id': self.id,
        })
        return True

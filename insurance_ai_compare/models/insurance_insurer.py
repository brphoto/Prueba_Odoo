# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PolizasAseguradoras(models.Model):
    _inherit = 'polizas.aseguradoras'

    image_128 = fields.Image(string='Logo', max_width=128, max_height=128)
    active = fields.Boolean(default=True)
    service_score = fields.Float(
        string='Calificación de servicio (0-5)', default=3.0,
        help='Valoración del broker sobre la atención de siniestros, tiempos de '
             'pago y servicio. Es un dato propio, no de la IA, y cuenta en el '
             'puntaje de «asistencias y servicio».')
    ai_extraction_hint = fields.Text(
        string='Pistas para leer sus cotizaciones',
        help='Cómo presenta esta aseguradora sus cotizaciones: dónde pone la prima '
             'total, cómo llama a sus coberturas, si el deducible va en una tabla '
             'aparte, etc. Se agrega a la instrucción de la IA solo para sus PDFs.')
    compare_offer_count = fields.Integer(compute='_compute_compare_offer_count', string='Cotizaciones')

    @api.constrains('service_score')
    def _check_service_score(self):
        for insurer in self:
            if not 0 <= insurer.service_score <= 5:
                raise ValidationError(_('La calificación de servicio va de 0 a 5.'))

    def _compute_compare_offer_count(self):
        counts = dict(self.env['insurance.compare.offer']._read_group(
            [('insurer_id', 'in', self.ids)], ['insurer_id'], ['__count']))
        for insurer in self:
            insurer.compare_offer_count = counts.get(insurer, 0)

    def action_view_compare_offers(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Cotizaciones de %s') % self.name,
            'res_model': 'insurance.compare.offer',
            'view_mode': 'list,form',
            'domain': [('insurer_id', '=', self.id)],
        }

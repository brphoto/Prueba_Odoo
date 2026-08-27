# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    experience_expected_lifetime_years = fields.Float(
        string='Vida útil estimada del cliente (años)',
        config_parameter='crm_customer_experience.expected_lifetime_years',
        default=3.0, help='Se usa en el LTV proyectado. Debe ser al menos 1 año.')
    experience_auto_nps_invitation = fields.Boolean(
        string='Preparar NPS después del pago',
        config_parameter='crm_customer_experience.auto_nps_invitation', default=True,
        help='El cron crea una invitación pendiente por cada factura de cliente pagada.')

# -*- coding: utf-8 -*-
from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    rfm_category = fields.Selection(
        related='partner_id.rfm_category', string="Categoría RFM", store=True, readonly=True)

# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    chatroom_lead_sla_hours = fields.Integer(
        string="SLA de oportunidad (horas)",
        config_parameter='chatroom_sales_intelligence.lead_sla_hours',
        default=2,
        help="Tiempo sin actividad hecha antes de liberar una oportunidad al pool.")

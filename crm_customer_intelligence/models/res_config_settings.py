# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Pesos del score RFM compuesto (Recencia/Frecuencia/Monto). No hace
    # falta que sumen exactamente 1: _cron_compute_rfm_scores() los
    # normaliza dividiendo cada uno por la suma de los tres, así que
    # cualquier combinación de valores relativos funciona (ej. 5/3/2 da
    # el mismo resultado que 0.5/0.3/0.2).
    rfm_weight_monetary = fields.Float(
        string="Peso Monto", config_parameter='crm_customer_intelligence.rfm_weight_monetary',
        default=0.5,
        help="Cuánto pesa el valor monetario de las compras en el score "
             "RFM compuesto.")
    rfm_weight_frequency = fields.Float(
        string="Peso Frecuencia", config_parameter='crm_customer_intelligence.rfm_weight_frequency',
        default=0.3,
        help="Cuánto pesa la cantidad de compras (facturas) en el score "
             "RFM compuesto.")
    rfm_weight_recency = fields.Float(
        string="Peso Recencia", config_parameter='crm_customer_intelligence.rfm_weight_recency',
        default=0.2,
        help="Cuánto pesa qué tan reciente fue la última compra en el "
             "score RFM compuesto.")

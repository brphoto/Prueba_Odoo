# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


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

    @api.constrains('rfm_weight_monetary', 'rfm_weight_frequency', 'rfm_weight_recency')
    def _check_rfm_weights(self):
        for settings in self:
            weights = (
                settings.rfm_weight_monetary,
                settings.rfm_weight_frequency,
                settings.rfm_weight_recency,
            )
            if any(weight < 0 for weight in weights):
                raise ValidationError(_('Los pesos RFM no pueden ser negativos.'))
            if not sum(weights):
                raise ValidationError(_('Configura al menos un peso RFM mayor que cero.'))

    rfm_category_method = fields.Selection(
        [('threshold', "Umbral fijo (Catálogo RFM)"),
         ('percentile', "Percentil de la cartera (20% / 30% / 50%)")],
        string="Método de corte A/B/C", default='threshold',
        config_parameter='crm_customer_intelligence.rfm_category_method',
        help="'Umbral fijo': compara el score de cada cliente contra los "
             "rangos configurados en Configuración > Catálogo RFM "
             "(editables ahí, sin código). 'Percentil de la cartera': "
             "ordena a todos los clientes por score y asigna A al 20% "
             "superior, B al 30% siguiente y C al 50% restante -las "
             "proporciones se mantienen estables aunque la cartera "
             "entera mejore o empeore, siguiendo la metodología RFM/"
             "Pareto clásica (ignora los rangos del Catálogo RFM).")

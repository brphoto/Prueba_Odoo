# -*- coding: utf-8 -*-
from odoo import fields, models


class CrmStage(models.Model):
    _inherit = 'crm.stage'

    stagnation_max_days = fields.Integer(
        string='Días máximos de estancamiento', default=30, required=True,
        help='Después de este tiempo la oportunidad entra en precaución, crítico o estancada según las reglas de la empresa.')
    stagnation_required_activities = fields.Integer(
        string='Actividades mínimas por etapa', default=0,
        help='Referencia para el score real/ficticia. Cero desactiva esta condición.')

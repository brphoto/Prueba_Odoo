# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class KpiTargetMixin(models.AbstractModel):
    """Objetivo de KPI, con alcance y período configurables.

    Antes vivía por duplicado, byte a byte, en chatroom_whatsapp
    (chatroom.kpi.target) y en crm_customer_intelligence (crm.kpi.target):
    ninguno de los dos módulos depende del otro, así que no podían
    compartir el código directamente sin este mixin. Cada módulo concreto
    agrega sus propios valores de scope_type (ej. 'salesperson'/'team' en
    CRM, 'agent'/'line' en Chatroom) con selection_add, y su propio campo
    Many2one para ese alcance extra."""
    _name = 'kpi.target.mixin'
    _description = 'Objetivo de KPI (mixin compartido)'

    scope_type = fields.Selection(
        [('global', 'Global'), ('company', 'Compañía')],
        string='Alcance', required=True, default='global')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    user_id = fields.Many2one('res.users', string='Usuario')
    target_value = fields.Float(required=True)
    goal_direction = fields.Selection([
        ('higher', 'Mayor o igual'), ('lower', 'Menor o igual'),
    ], string='Cumplimiento', required=True, default='higher')
    active = fields.Boolean(default=True)
    period_type = fields.Selection([
        ('all', 'Todo el tiempo'), ('monthly', 'Mensual'),
        ('quarterly', 'Trimestral'), ('yearly', 'Anual'), ('custom', 'Personalizado'),
    ], string='Período del objetivo', default='all', required=True)
    date_from = fields.Date(string='Desde')
    date_to = fields.Date(string='Hasta')

    @api.constrains('period_type', 'date_from', 'date_to')
    def _check_period_dates(self):
        for record in self:
            if record.period_type == 'custom' and record.date_from and record.date_to \
                    and record.date_from > record.date_to:
                raise ValidationError(_(
                    'La fecha inicial no puede ser posterior a la fecha final.'))

    def is_current_period(self, today=None):
        self.ensure_one()
        today = today or fields.Date.context_today(self)
        if self.period_type == 'custom':
            return (not self.date_from or self.date_from <= today) and \
                   (not self.date_to or today <= self.date_to)
        return True

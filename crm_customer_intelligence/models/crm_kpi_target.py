# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class CrmKpiTarget(models.Model):
    _name = 'crm.kpi.target'
    _inherit = ['kpi.target.mixin']
    _description = 'Objetivo de KPI comercial'
    _order = 'kpi_id, scope_type, id'

    kpi_id = fields.Many2one('crm.kpi.definition', required=True, ondelete='cascade')
    scope_type = fields.Selection(selection_add=[
        ('salesperson', 'Vendedor'), ('team', 'Equipo de ventas'),
    ], ondelete={'salesperson': 'set default', 'team': 'set default'})
    user_id = fields.Many2one('res.users', string='Vendedor')
    team_id = fields.Many2one('crm.team', string='Equipo de ventas')

    @api.constrains('scope_type', 'user_id', 'team_id')
    def _check_scope(self):
        for record in self:
            if record.scope_type == 'salesperson' and not record.user_id:
                raise ValidationError(_('Selecciona el vendedor del objetivo.'))
            if record.scope_type == 'team' and not record.team_id:
                raise ValidationError(_('Selecciona el equipo del objetivo.'))

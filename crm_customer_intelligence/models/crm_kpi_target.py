# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class CrmKpiTarget(models.Model):
    _name = 'crm.kpi.target'
    _description = 'Objetivo de KPI comercial'
    _order = 'kpi_id, scope_type, id'

    kpi_id = fields.Many2one('crm.kpi.definition', required=True, ondelete='cascade')
    scope_type = fields.Selection([
        ('global', 'Global'), ('company', 'Compañía'),
        ('salesperson', 'Vendedor'), ('team', 'Equipo de ventas'),
    ], string='Alcance', required=True, default='global')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    user_id = fields.Many2one('res.users', string='Vendedor')
    team_id = fields.Many2one('crm.team', string='Equipo de ventas')
    target_value = fields.Float(required=True)
    goal_direction = fields.Selection([
        ('higher', 'Mayor o igual'), ('lower', 'Menor o igual'),
    ], string='Cumplimiento', required=True, default='higher')
    active = fields.Boolean(default=True)

    @api.constrains('scope_type', 'user_id', 'team_id')
    def _check_scope(self):
        for record in self:
            if record.scope_type == 'salesperson' and not record.user_id:
                raise ValidationError('Selecciona el vendedor del objetivo.')
            if record.scope_type == 'team' and not record.team_id:
                raise ValidationError('Selecciona el equipo del objetivo.')

# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ChatroomAiTool(models.Model):
    _name = 'chatroom.ai.tool'
    _description = 'Herramienta autorizada del agente IA'
    _order = 'sequence, name'

    name = fields.Char(string='Nombre', required=True)
    key = fields.Char(string='Clave técnica', required=True, index=True)
    description = fields.Text(string='Descripción')
    model_name = fields.Char(string='Modelo Odoo')
    operation = fields.Char(string='Operación')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    requires_approval = fields.Boolean(string='Requiere aprobación', default=True)
    group_id = fields.Many2one('res.groups', string='Grupo autorizado')
    company_id = fields.Many2one('res.company', string='Empresa', default=lambda self: self.env.company)

    _key_unique = models.Constraint(
        'unique(key)', 'La clave técnica de la herramienta debe ser única.')

    @api.model
    def enabled_for_user(self):
        tools = self.search([
            ('active', '=', True),
            '|', ('company_id', '=', False), ('company_id', '=', self.env.company.id),
            '|', ('group_id', '=', False), ('group_id', 'in', self.env.user.groups_id.ids),
        ])
        return tools

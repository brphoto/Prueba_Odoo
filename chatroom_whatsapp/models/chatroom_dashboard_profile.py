# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ChatroomDashboardProfile(models.Model):
    _name = 'chatroom.dashboard.profile'
    _description = 'Perfil guardado del dashboard de Chatroom'
    _order = 'name'

    name = fields.Char(string='Nombre del perfil', required=True)
    active = fields.Boolean(default=True)
    dashboard_type = fields.Selection([
        ('chatroom', 'Dashboard de Chatroom'),
        ('executive', 'Dashboard ejecutivo'),
    ], string='Dashboard', required=True, default='chatroom')
    user_id = fields.Many2one('res.users', string='Usuario', default=lambda self: self.env.user)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    period_days = fields.Selection([
        ('7', 'Últimos 7 días'), ('30', 'Últimos 30 días'),
        ('90', 'Últimos 90 días'), ('365', 'Últimos 12 meses'),
        ('0', 'Todo el historial'),
    ], string='Período', default='30', required=True)
    widget_ids = fields.Many2many(
        'chatroom.dashboard.widget', 'chatroom_profile_widget_rel',
        'profile_id', 'widget_id', string='Widgets visibles')
    is_default = fields.Boolean(string='Usar por defecto')

    @api.model
    def get_available_profiles(self, dashboard_type='chatroom'):
        profiles = self.search([
            ('active', '=', True), ('dashboard_type', '=', dashboard_type),
            ('company_id', '=', self.env.company.id),
            '|', ('user_id', '=', self.env.user.id), ('user_id', '=', False),
        ], order='is_default desc, name')
        return [{
            'id': profile.id, 'name': profile.name,
            'period_days': int(profile.period_days),
            'widget_ids': profile.widget_ids.ids,
        } for profile in profiles]

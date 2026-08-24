# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    chatroom_ai_model_id = fields.Many2one(
        'chatroom.ai.provider.model', string='Modelo activo de Chatroom',
        domain=[('active', '=', True), ('supports_chat', '=', True)],
    )
    chatroom_ai_admin_api_key = fields.Char(
        string='Admin API Key para consumo',
        config_parameter='chatroom_whatsapp.ai_admin_api_key',
    )
    chatroom_ai_usage_days = fields.Integer(
        string='Periodo de consulta (dias)', default=31,
        config_parameter='chatroom_whatsapp.ai_usage_days',
    )
    chatroom_ai_monthly_budget = fields.Float(
        string='Presupuesto mensual de referencia', digits=(16, 2),
        config_parameter='chatroom_whatsapp.ai_monthly_budget',
        help='Referencia interna para alertas. No modifica el limite de OpenAI.',
    )

    @api.model
    def get_values(self):
        values = super().get_values()
        raw_id = self.env['ir.config_parameter'].sudo().get_param('chatroom_whatsapp.ai_model_id')
        try:
            values['chatroom_ai_model_id'] = int(raw_id) if raw_id else False
        except (TypeError, ValueError):
            values['chatroom_ai_model_id'] = False
        return values

    def set_values(self):
        super().set_values()
        self.env['ir.config_parameter'].sudo().set_param(
            'chatroom_whatsapp.ai_model_id', str(self.chatroom_ai_model_id.id or ''))

    def action_sync_ai_models(self):
        self.ensure_one()
        return self.env['chatroom.ai.provider.model'].action_sync_from_provider()

    def action_refresh_ai_usage(self):
        self.ensure_one()
        return self.env['chatroom.ai.usage.snapshot'].action_refresh()

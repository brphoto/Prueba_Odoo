# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    chatroom_ai_model_id = fields.Many2one(
        'chatroom.ai.provider.model', string='Modelo activo de Chatroom',
        domain=[('active', '=', True), ('supports_chat', '=', True)],
    )
    chatroom_ai_model_reply_id = fields.Many2one(
        'chatroom.ai.provider.model', string='Modelo para respuestas',
        domain=[('active', '=', True), ('supports_chat', '=', True)],
    )
    chatroom_ai_model_summary_id = fields.Many2one(
        'chatroom.ai.provider.model', string='Modelo para resumenes',
        domain=[('active', '=', True), ('supports_chat', '=', True)],
    )
    chatroom_ai_model_classification_id = fields.Many2one(
        'chatroom.ai.provider.model', string='Modelo para clasificacion',
        domain=[('active', '=', True), ('supports_chat', '=', True)],
    )
    chatroom_ai_model_agent_id = fields.Many2one(
        'chatroom.ai.provider.model', string='Modelo para agente',
        domain=[('active', '=', True), ('supports_chat', '=', True)],
    )
    chatroom_ai_fallback_model_id = fields.Many2one(
        'chatroom.ai.provider.model', string='Modelo de respaldo',
        domain=[('active', '=', True), ('supports_chat', '=', True)],
        help='Se usa automaticamente si el modelo principal no responde o no esta disponible.',
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
    chatroom_ai_usage_auto_refresh = fields.Boolean(
        string='Actualizar consumo automaticamente',
        config_parameter='chatroom_whatsapp.ai_usage_auto_refresh',
        help='Crea un resumen diario y alerta a los administradores cuando se alcanza el presupuesto.',
    )

    @api.model
    def get_values(self):
        values = super().get_values()
        icp = self.env['ir.config_parameter'].sudo()
        fields_by_param = {
            'chatroom_ai_model_id': 'chatroom_whatsapp.ai_model_id',
            'chatroom_ai_model_reply_id': 'chatroom_whatsapp.ai_model_reply_id',
            'chatroom_ai_model_summary_id': 'chatroom_whatsapp.ai_model_summary_id',
            'chatroom_ai_model_classification_id': 'chatroom_whatsapp.ai_model_classification_id',
            'chatroom_ai_model_agent_id': 'chatroom_whatsapp.ai_model_agent_id',
            'chatroom_ai_fallback_model_id': 'chatroom_whatsapp.ai_fallback_model_id',
        }
        for field_name, param_name in fields_by_param.items():
            raw_id = icp.get_param(param_name)
            try:
                values[field_name] = int(raw_id) if raw_id else False
            except (TypeError, ValueError):
                values[field_name] = False
        return values

    def set_values(self):
        super().set_values()
        values = {
            'chatroom_whatsapp.ai_model_id': self.chatroom_ai_model_id.id,
            'chatroom_whatsapp.ai_model_reply_id': self.chatroom_ai_model_reply_id.id,
            'chatroom_whatsapp.ai_model_summary_id': self.chatroom_ai_model_summary_id.id,
            'chatroom_whatsapp.ai_model_classification_id': self.chatroom_ai_model_classification_id.id,
            'chatroom_whatsapp.ai_model_agent_id': self.chatroom_ai_model_agent_id.id,
            'chatroom_whatsapp.ai_fallback_model_id': self.chatroom_ai_fallback_model_id.id,
        }
        for key, value in values.items():
            self.env['ir.config_parameter'].sudo().set_param(key, str(value or ''))

    def action_sync_ai_models(self):
        self.ensure_one()
        return self.env['chatroom.ai.provider.model'].action_sync_from_provider()

    def action_refresh_ai_usage(self):
        self.ensure_one()
        return self.env['chatroom.ai.usage.snapshot'].action_refresh()

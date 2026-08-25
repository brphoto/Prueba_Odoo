# -*- coding: utf-8 -*-
import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError


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
    chatroom_ai_model_next_action_id = fields.Many2one(
        'chatroom.ai.provider.model', string='Modelo para proxima accion',
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
            'chatroom_ai_model_next_action_id': 'chatroom_whatsapp.ai_model_next_action_id',
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
            'chatroom_whatsapp.ai_model_next_action_id': self.chatroom_ai_model_next_action_id.id,
            'chatroom_whatsapp.ai_model_agent_id': self.chatroom_ai_model_agent_id.id,
            'chatroom_whatsapp.ai_fallback_model_id': self.chatroom_ai_fallback_model_id.id,
        }
        for key, value in values.items():
            self.env['ir.config_parameter'].sudo().set_param(key, str(value or ''))

    def action_sync_ai_models(self):
        self.ensure_one()
        return self.env['chatroom.ai.provider.model'].action_sync_from_provider()

    def action_test_ai_connection(self):
        """Valida endpoint y credencial sin consumir una respuesta del modelo."""
        self.ensure_one()
        icp = self.env['ir.config_parameter'].sudo()
        api_key = (icp.get_param('chatroom_whatsapp.ai_api_key') or '').strip()
        base = self.env['chatroom.ai.provider.model']._api_base()
        if not api_key or not base:
            raise UserError(_('Configura primero el endpoint y la API Key de IA.'))
        try:
            response = requests.get(
                '%s/models' % base,
                headers={'Authorization': 'Bearer %s' % api_key},
                timeout=15,
            )
            response.raise_for_status()
            payload = response.json()
            models_count = len(payload.get('data', [])) if isinstance(payload, dict) else 0
        except (requests.RequestException, ValueError, TypeError) as exc:
            raise UserError(_('No se pudo conectar con el proveedor de IA: %s') % exc) from exc
        icp.set_param('chatroom_whatsapp.ai_last_health_check', fields.Datetime.now())
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('ConexiÃ³n IA correcta'),
                'message': _('El endpoint respondiÃ³ correctamente y devolviÃ³ %s modelo(s).') % models_count,
                'type': 'success',
                'sticky': False,
            },
        }

    def action_refresh_ai_usage(self):
        self.ensure_one()
        return self.env['chatroom.ai.usage.snapshot'].action_refresh()

    def action_open_ai_sandbox(self):
        return self.env.ref('chatroom_ai_usage.action_chatroom_ai_sandbox').read()[0]

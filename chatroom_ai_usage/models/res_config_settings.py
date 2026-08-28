# -*- coding: utf-8 -*-
import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


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
        'chatroom.ai.provider.model', string='Modelo para resúmenes',
        domain=[('active', '=', True), ('supports_chat', '=', True)],
    )
    chatroom_ai_model_classification_id = fields.Many2one(
        'chatroom.ai.provider.model', string='Modelo para clasificación',
        domain=[('active', '=', True), ('supports_chat', '=', True)],
    )
    chatroom_ai_model_next_action_id = fields.Many2one(
        'chatroom.ai.provider.model', string='Modelo para próxima acción',
        domain=[('active', '=', True), ('supports_chat', '=', True)],
    )
    chatroom_ai_model_agent_id = fields.Many2one(
        'chatroom.ai.provider.model', string='Modelo para agente',
        domain=[('active', '=', True), ('supports_chat', '=', True)],
    )
    chatroom_ai_fallback_model_id = fields.Many2one(
        'chatroom.ai.provider.model', string='Modelo de respaldo',
        domain=[('active', '=', True), ('supports_chat', '=', True)],
        help='Se usa automáticamente si el modelo principal no responde o no está disponible.',
    )
    chatroom_ai_admin_api_key = fields.Char(
        string='Admin API Key para consumo',
        config_parameter='chatroom_whatsapp.ai_admin_api_key',
    )
    chatroom_ai_usage_connection_status = fields.Selection([
        ('missing_admin_key', 'Falta Admin API Key'),
        ('ok', 'Conectado'),
        ('error', 'Revisar permisos'),
    ], string='Estado de consumo oficial', compute='_compute_ai_usage_connection_status')
    chatroom_ai_usage_last_sync = fields.Datetime(
        string='Última comprobación', compute='_compute_ai_usage_connection_status',
    )
    chatroom_ai_usage_last_error = fields.Text(
        string='Detalle de la última comprobación', compute='_compute_ai_usage_connection_status',
    )
    chatroom_ai_usage_days = fields.Integer(
        string='Período de consulta (días)', default=31,
        config_parameter='chatroom_whatsapp.ai_usage_days',
    )
    chatroom_ai_monthly_budget = fields.Float(
        string='Presupuesto mensual de referencia', digits=(16, 2),
        config_parameter='chatroom_whatsapp.ai_monthly_budget',
        help='Referencia interna para alertas. No modifica el limite de OpenAI.',
    )
    chatroom_ai_daily_token_limit = fields.Integer(
        string='Límite diario de tokens', default=0,
        config_parameter='chatroom_whatsapp.ai_daily_token_limit',
        help='0 permite consumo ilimitado. Si se alcanza el límite, la IA externa se pausa hasta el día siguiente.',
    )
    chatroom_ai_daily_request_limit = fields.Integer(
        string='Límite diario de solicitudes', default=0,
        config_parameter='chatroom_whatsapp.ai_daily_request_limit',
        help='0 permite solicitudes ilimitadas. Sirve como protección adicional ante automatizaciones mal configuradas.',
    )
    chatroom_ai_usage_auto_refresh = fields.Boolean(
        string='Actualizar consumo automáticamente',
        config_parameter='chatroom_whatsapp.ai_usage_auto_refresh',
        help='Crea un resumen diario y alerta a los administradores cuando se alcanza el presupuesto.',
    )
    chatroom_ai_history_messages = fields.Integer(
        string='Mensajes recientes para la IA', default=6,
        config_parameter='chatroom_ai.history_messages',
        help='Cantidad de mensajes recientes que se envían al proveedor. Un valor bajo reduce tokens y mantiene el contexto operativo.',
    )
    chatroom_ai_knowledge_context_max_chars = fields.Integer(
        string='Máximo de conocimiento enviado (caracteres)', default=7000,
        config_parameter='chatroom_ai.knowledge_context_max_chars',
        help='Límite del contexto de manuales y datos relevantes. 7000 caracteres son aproximadamente 1750 tokens de entrada.',
    )
    chatroom_ai_knowledge_context_max_chunks = fields.Integer(
        string='Fragmentos relevantes por consulta', default=3,
        config_parameter='chatroom_ai.knowledge_context_max_chunks',
        help='Cantidad de fragmentos indexados que se recuperan para cada pregunta.',
    )
    chatroom_ai_knowledge_product_limit = fields.Integer(
        string='Productos coincidentes como máximo', default=5,
        config_parameter='chatroom_ai.knowledge_product_limit',
        help='La IA consulta productos vivos de Odoo solo cuando la pregunta contiene términos de producto.',
    )

    @api.constrains(
        'chatroom_ai_usage_days', 'chatroom_ai_daily_token_limit',
        'chatroom_ai_daily_request_limit', 'chatroom_ai_history_messages',
        'chatroom_ai_knowledge_context_max_chars',
        'chatroom_ai_knowledge_context_max_chunks',
        'chatroom_ai_knowledge_product_limit',
    )
    def _check_ai_resource_limits(self):
        """Evita configuraciones que disparen el consumo o rompan el contexto."""
        for settings in self:
            if not 1 <= settings.chatroom_ai_usage_days <= 31:
                raise ValidationError(_('El periodo de consulta debe estar entre 1 y 31 días.'))
            if settings.chatroom_ai_daily_token_limit < 0:
                raise ValidationError(_('El límite diario de tokens no puede ser negativo.'))
            if settings.chatroom_ai_daily_request_limit < 0:
                raise ValidationError(_('El límite diario de solicitudes no puede ser negativo.'))
            if not 1 <= settings.chatroom_ai_history_messages <= 30:
                raise ValidationError(_('La cantidad de mensajes para la IA debe estar entre 1 y 30.'))
            if not 1000 <= settings.chatroom_ai_knowledge_context_max_chars <= 16000:
                raise ValidationError(_('El conocimiento enviado debe estar entre 1.000 y 16.000 caracteres.'))
            if not 1 <= settings.chatroom_ai_knowledge_context_max_chunks <= 10:
                raise ValidationError(_('Los fragmentos relevantes deben estar entre 1 y 10.'))
            if not 1 <= settings.chatroom_ai_knowledge_product_limit <= 20:
                raise ValidationError(_('Los productos coincidentes deben estar entre 1 y 20.'))

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

    def _compute_ai_usage_connection_status(self):
        icp = self.env['ir.config_parameter'].sudo()
        status = icp.get_param('chatroom_whatsapp.ai_usage_last_status') or (
            'ok' if (icp.get_param('chatroom_whatsapp.ai_admin_api_key') or '').strip()
            else 'missing_admin_key'
        )
        for settings in self:
            settings.chatroom_ai_usage_connection_status = status if status in (
                'missing_admin_key', 'ok', 'error'
            ) else 'missing_admin_key'
            raw_date = icp.get_param('chatroom_whatsapp.ai_usage_last_sync') or False
            settings.chatroom_ai_usage_last_sync = fields.Datetime.to_datetime(raw_date) if raw_date else False
            settings.chatroom_ai_usage_last_error = icp.get_param(
                'chatroom_whatsapp.ai_usage_last_error'
            ) or False

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
                'title': _('Conexión IA correcta'),
                'message': _('El endpoint respondió correctamente y devolvió %s modelo(s).') % models_count,
                'type': 'success',
                'sticky': False,
            },
        }

    def action_refresh_ai_usage(self):
        self.ensure_one()
        return self.env['chatroom.ai.usage.snapshot'].action_refresh()

    def action_test_ai_usage_connection(self):
        self.ensure_one()
        return self.env['chatroom.ai.usage.snapshot'].action_test_platform_connection()

    def action_open_ai_billing(self):
        self.ensure_one()
        return self.env['chatroom.ai.usage.snapshot'].action_open_platform_billing()

    def action_open_ai_sandbox(self):
        return self.env.ref('chatroom_ai_usage.action_chatroom_ai_sandbox').read()[0]

    def action_open_ai_setup_wizard(self):
        """Open the guided setup with the current database values preloaded."""
        self.ensure_one()
        return self.env.ref('chatroom_ai_usage.action_chatroom_ai_setup_wizard').read()[0]

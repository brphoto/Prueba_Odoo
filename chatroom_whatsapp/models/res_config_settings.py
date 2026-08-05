# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # -- Meta / WhatsApp Business Cloud API (conexión directa, sin BSP) --
    whatsapp_graph_api_version = fields.Char(
        string="Versión Graph API",
        config_parameter='chatroom_whatsapp.graph_api_version',
        default='v20.0',
        help="Versión de la Graph API de Meta, ej: v20.0")
    whatsapp_phone_number_id = fields.Char(
        string="Phone Number ID",
        config_parameter='chatroom_whatsapp.phone_number_id',
        help="ID del número de teléfono de WhatsApp Business "
             "(Meta Business Suite > WhatsApp > Configuración de la API)")
    whatsapp_business_account_id = fields.Char(
        string="WhatsApp Business Account ID (WABA)",
        config_parameter='chatroom_whatsapp.business_account_id')
    whatsapp_access_token = fields.Char(
        string="Token de acceso permanente",
        config_parameter='chatroom_whatsapp.access_token',
        help="Token permanente de un usuario de sistema (System User) con "
             "los permisos whatsapp_business_messaging y "
             "whatsapp_business_management. No se usa ningún proveedor "
             "externo: la llamada va directo a graph.facebook.com")
    whatsapp_webhook_verify_token = fields.Char(
        string="Webhook Verify Token",
        config_parameter='chatroom_whatsapp.webhook_verify_token',
        help="Token arbitrario que debes definir aquí y repetir en la "
             "configuración del Webhook dentro de Meta App Dashboard")
    whatsapp_app_secret = fields.Char(
        string="App Secret (Meta App)",
        config_parameter='chatroom_whatsapp.app_secret',
        help="App Secret de la App de Meta. Se usa para verificar la "
             "firma X-Hub-Signature-256 de cada webhook y así confirmar "
             "que la petición viene realmente de Meta.")
    whatsapp_webhook_url = fields.Char(
        string="Webhook URL", compute='_compute_whatsapp_webhook_url')

    # -- Sugerencias de respuesta con IA (cualquier proveedor LLM) --
    chatroom_ai_enabled = fields.Boolean(
        string="Activar sugerencias con IA",
        config_parameter='chatroom_whatsapp.ai_enabled')
    chatroom_ai_provider_url = fields.Char(
        string="Endpoint API IA (chat/completions)",
        config_parameter='chatroom_whatsapp.ai_provider_url',
        help="Endpoint HTTP compatible con el formato "
             "'chat completions' (OpenAI, Anthropic, Azure OpenAI, "
             "modelo propio, etc.)")
    chatroom_ai_api_key = fields.Char(
        string="API Key del proveedor de IA",
        config_parameter='chatroom_whatsapp.ai_api_key')
    chatroom_ai_model = fields.Char(
        string="Modelo IA",
        config_parameter='chatroom_whatsapp.ai_model',
        default='gpt-4o-mini')

    def _compute_whatsapp_webhook_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param(
            'web.base.url', default='')
        for rec in self:
            rec.whatsapp_webhook_url = f"{base_url}/chatroom_whatsapp/webhook"

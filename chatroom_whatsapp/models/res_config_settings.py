# -*- coding: utf-8 -*-
import logging

import requests

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = ['res.config.settings', 'chatroom.meta.mixin']

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
    whatsapp_last_webhook_display = fields.Char(
        string="Último webhook recibido", compute='_compute_whatsapp_last_webhook_display',
        help="Última vez que Meta nos mandó un evento (mensaje o cambio de "
             "estado), de cualquier línea. Si nunca llegó ninguno, revisá "
             "que la URL del Webhook esté bien registrada en Meta.")
    chatroom_auto_assign = fields.Boolean(
        string="Asignación automática de conversaciones",
        config_parameter='chatroom_whatsapp.auto_assign', default=True,
        help="Reparte las conversaciones nuevas entre los agentes del "
             "grupo 'Chatroom / Agente', priorizando al que menos "
             "conversaciones abiertas tenga.")
    chatroom_sla_enabled = fields.Boolean(
        string="Activar SLA de primera respuesta",
        config_parameter='chatroom_whatsapp.sla_enabled', default=True)
    chatroom_sla_yellow_minutes = fields.Integer(
        string="Aviso amarillo después de (minutos)",
        config_parameter='chatroom_whatsapp.sla_yellow_minutes', default=10)
    chatroom_sla_red_minutes = fields.Integer(
        string="Vencimiento rojo después de (minutos)",
        config_parameter='chatroom_whatsapp.sla_red_minutes', default=15)
    chatroom_sla_auto_reassign = fields.Boolean(
        string="Liberar y reasignar automáticamente al vencer",
        config_parameter='chatroom_whatsapp.sla_auto_reassign', default=True,
        help="Quita la conversación al agente que no respondió y la entrega "
             "al siguiente agente disponible con menos carga.")

    # -- Messenger / Instagram (misma App de Meta, token de Página) --
    chatroom_meta_page_access_token = fields.Char(
        string="Token de Página (Messenger/Instagram)",
        config_parameter='chatroom_whatsapp.meta_page_access_token',
        help="Page Access Token de la Página de Facebook/Instagram "
             "conectada a tu App de Meta. Solo se usa para enviar por "
             "Messenger/Instagram; WhatsApp usa su propio token arriba.")

    # -- Cumplimiento: opt-out / consentimiento --
    chatroom_opt_out_keywords = fields.Char(
        string="Palabras clave de baja",
        config_parameter='chatroom_whatsapp.opt_out_keywords',
        default='stop,baja,cancelar,unsubscribe',
        help="Lista separada por comas. Si un cliente escribe exactamente "
             "una de estas palabras, se marca como dado de baja y no se le "
             "vuelve a escribir hasta que se dé de alta.")
    chatroom_opt_in_keywords = fields.Char(
        string="Palabras clave de alta",
        config_parameter='chatroom_whatsapp.opt_in_keywords',
        default='iniciar,start,alta',
        help="Lista separada por comas para reactivar a un contacto dado "
             "de baja.")

    # -- Horario de atención: aviso automático fuera de hora --
    chatroom_business_hours_enabled = fields.Boolean(
        string="Activar horario de atención",
        config_parameter='chatroom_whatsapp.business_hours_enabled',
        help="Fuera de este horario, la primera vez que escriba cada "
             "contacto en el día se le manda un aviso automático en vez "
             "de dejarlo esperando toda la noche sin saber que nadie va "
             "a contestar hasta la mañana siguiente.")
    chatroom_business_hours_start = fields.Float(
        string="Hora de inicio", config_parameter='chatroom_whatsapp.business_hours_start',
        default=9.0)
    chatroom_business_hours_end = fields.Float(
        string="Hora de fin", config_parameter='chatroom_whatsapp.business_hours_end',
        default=18.0)
    chatroom_business_hours_weekdays = fields.Char(
        string="Días (0=lunes ... 6=domingo)",
        config_parameter='chatroom_whatsapp.business_hours_weekdays',
        default='0,1,2,3,4',
        help="Lista separada por comas. Por defecto lunes a viernes.")
    chatroom_business_hours_tz = fields.Char(
        string="Zona horaria", config_parameter='chatroom_whatsapp.business_hours_tz',
        help="Ej: America/Guayaquil. Si se deja vacío, se usa la zona "
             "horaria del usuario que instaló el módulo.")
    chatroom_business_hours_away_message = fields.Char(
        string="Mensaje fuera de horario",
        config_parameter='chatroom_whatsapp.business_hours_away_message',
        # 'res.config.settings' solo permite boolean/integer/float/char/
        # selection/many2one/datetime en campos con config_parameter
        # (ir_config._get_classified_fields los valida a mano) — un
        # Text revienta el onchange de Ajustes apenas se abre la
        # pantalla, no solo al guardar. Char no tiene límite de
        # caracteres real en Odoo, así que no pierde nada.
        default="Gracias por escribirnos. En este momento estamos fuera "
                "de nuestro horario de atención; te respondemos apenas "
                "volvamos.")

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
    chatroom_ai_auto_classify = fields.Boolean(
        string="Clasificar intención automáticamente",
        config_parameter='chatroom_whatsapp.ai_auto_classify',
        help="Al recibir un mensaje, la IA etiqueta la conversación como "
             "Consulta / Venta / Soporte / Queja.")
    chatroom_ai_auto_lead = fields.Boolean(
        string="Crear Oportunidad automáticamente",
        config_parameter='chatroom_whatsapp.ai_auto_lead',
        help="Si la IA clasifica el mensaje como 'Venta' y la "
             "conversación no tiene una oportunidad vinculada, se crea y "
             "se ancla automáticamente. Requiere activar la clasificación.")
    chatroom_ai_auto_reply = fields.Boolean(
        string="Responder automáticamente con IA",
        config_parameter='chatroom_whatsapp.ai_auto_reply',
        help="Envía la sugerencia de IA sin intervención humana. "
             "Actívalo solo si confías en las respuestas del modelo/prompt "
             "configurado: no hay revisión previa de un agente.")
    chatroom_ai_auto_price_reply = fields.Boolean(
        string="Responder consultas de precio con datos reales",
        config_parameter='chatroom_whatsapp.ai_auto_price_reply',
        help="Si el mensaje del cliente menciona el nombre de un producto "
             "vendible, se le contesta automáticamente con el precio real "
             "de ese producto (tomado de Odoo, no inventado por el "
             "modelo). Se ignora si 'Vendedor automático' (abajo) está "
             "activo, porque ese modo ya incluye precios reales.")
    chatroom_ai_auto_order_reply = fields.Boolean(
        string="Vendedor automático (armar pedidos)",
        config_parameter='chatroom_whatsapp.ai_auto_order_reply',
        help="La IA arma un carrito charlando con el cliente (usando "
             "solo productos y precios reales de Odoo) y, cuando el "
             "cliente confirma, crea una Cotización real en borrador — "
             "nunca la confirma sola, siempre queda pendiente de que un "
             "agente la revise. Reemplaza a 'Responder consultas de "
             "precio' y a 'Responder automáticamente' mientras esté "
             "activo. La IA se pausa sola en cualquier conversación en "
             "cuanto un agente humano manda un mensaje real (o se puede "
             "pausar/reactivar a mano desde el encabezado del chat).")

    def _compute_whatsapp_webhook_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param(
            'web.base.url', default='')
        for rec in self:
            rec.whatsapp_webhook_url = f"{base_url}/chatroom_whatsapp/webhook"

    def _compute_whatsapp_last_webhook_display(self):
        raw = self.env['ir.config_parameter'].sudo().get_param(
            'chatroom_whatsapp.last_webhook_at')
        last = fields.Datetime.to_datetime(raw) if raw else False
        for rec in self:
            rec.whatsapp_last_webhook_display = self._format_relative_time(last)

    def action_test_whatsapp_connection(self):
        """Valida el token y el Phone Number ID contra la Graph API real,
        sin enviar ningún mensaje (solo lee los datos públicos del
        número). Así se descubre un token vencido o mal copiado antes de
        intentar mandarle algo a un cliente de verdad."""
        self.ensure_one()
        token, phone_number_id, api_version = self._get_meta_credentials()
        url = f"https://graph.facebook.com/{api_version}/{phone_number_id}"
        try:
            response = self._meta_request(
                'GET', url,
                params={'fields': 'display_phone_number,verified_name,quality_rating'},
                headers={"Authorization": f"Bearer {token}"},
                timeout=15, max_retries=0,
            )
            data = response.json()
            if response.status_code >= 400:
                error = data.get('error', {}).get('message', str(data))
                raise UserError(_("Meta respondió con un error: %s") % error)
        except requests.RequestException as exc:
            _logger.error("Error probando la conexión con Meta: %s", exc)
            raise UserError(_("No se pudo conectar con Meta: %s") % exc)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Conexión OK"),
                'message': _("Número verificado: %(name)s (%(phone)s). Calidad: %(quality)s.") % {
                    'name': data.get('verified_name') or '?',
                    'phone': data.get('display_phone_number') or phone_number_id,
                    'quality': data.get('quality_rating') or '?',
                },
                'type': 'success',
                'sticky': False,
            },
        }

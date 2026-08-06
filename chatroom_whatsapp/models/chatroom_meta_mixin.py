# -*- coding: utf-8 -*-
import logging
import time

import requests

from odoo import _, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Códigos ante los que vale la pena reintentar: 429 (límite de tasa) y
# errores transitorios del lado de Meta. No se reintentan 4xx de negocio
# (token inválido, número mal formado, etc.): esos no se arreglan solos.
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class ChatroomMetaMixin(models.AbstractModel):
    """Credenciales compartidas para hablar directo con la Graph API de
    Meta (WhatsApp Business Cloud API), sin proveedores externos."""
    _name = 'chatroom.meta.mixin'
    _description = "Credenciales de Meta Graph API (mixin)"

    @staticmethod
    def _meta_request(method, url, max_retries=2, **kwargs):
        """Llama a la Graph API con reintentos cortos (backoff exponencial)
        ante 429 o errores 5xx transitorios. Un solo fallo de red no debe
        tumbar el envío de un mensaje si Meta se recupera en un segundo."""
        attempt = 0
        while True:
            try:
                response = requests.request(method, url, timeout=kwargs.pop('timeout', 15), **kwargs)
            except requests.RequestException:
                if attempt >= max_retries:
                    raise
                response = None
            if response is not None and response.status_code not in RETRYABLE_STATUS_CODES:
                return response
            if attempt >= max_retries:
                return response
            wait = 0.5 * (2 ** attempt)
            _logger.warning(
                "Meta Graph API respondió %s en %s, reintento %s/%s en %.1fs",
                response.status_code if response is not None else 'sin respuesta',
                url, attempt + 1, max_retries, wait)
            time.sleep(wait)
            attempt += 1

    def _get_meta_credentials(self):
        icp = self.env['ir.config_parameter'].sudo()
        token = icp.get_param('chatroom_whatsapp.access_token')
        phone_number_id = icp.get_param('chatroom_whatsapp.phone_number_id')
        api_version = icp.get_param('chatroom_whatsapp.graph_api_version', 'v20.0')
        if not token or not phone_number_id:
            raise UserError(_(
                "Configura el Token de acceso y el Phone Number ID en "
                "Ajustes > Chatroom WhatsApp antes de enviar mensajes."))
        return token, phone_number_id, api_version

    def _get_meta_waba_credentials(self):
        icp = self.env['ir.config_parameter'].sudo()
        token = icp.get_param('chatroom_whatsapp.access_token')
        waba_id = icp.get_param('chatroom_whatsapp.business_account_id')
        api_version = icp.get_param('chatroom_whatsapp.graph_api_version', 'v20.0')
        if not token or not waba_id:
            raise UserError(_(
                "Configura el Token de acceso y el WhatsApp Business "
                "Account ID en Ajustes > Chatroom WhatsApp."))
        return token, waba_id, api_version

    def _get_meta_page_credentials(self):
        """Credenciales para Messenger/Instagram: usan el Token de Página
        de Meta, distinto del token de WhatsApp aunque estén en la misma
        App (Facebook Login for Business > Page Access Token)."""
        icp = self.env['ir.config_parameter'].sudo()
        token = icp.get_param('chatroom_whatsapp.meta_page_access_token')
        api_version = icp.get_param('chatroom_whatsapp.graph_api_version', 'v20.0')
        if not token:
            raise UserError(_(
                "Configura el Token de Página de Meta en Ajustes > "
                "Chatroom WhatsApp para enviar por Messenger/Instagram."))
        return token, api_version

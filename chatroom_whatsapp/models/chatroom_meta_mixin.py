# -*- coding: utf-8 -*-
from odoo import _, models
from odoo.exceptions import UserError


class ChatroomMetaMixin(models.AbstractModel):
    """Credenciales compartidas para hablar directo con la Graph API de
    Meta (WhatsApp Business Cloud API), sin proveedores externos."""
    _name = 'chatroom.meta.mixin'
    _description = "Credenciales de Meta Graph API (mixin)"

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

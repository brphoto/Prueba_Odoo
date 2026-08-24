# -*- coding: utf-8 -*-
from odoo import models


class ChatroomChannel(models.Model):
    _inherit = 'chatroom.channel'

    def _ai_get_credentials(self):
        credentials = super()._ai_get_credentials()
        if not credentials or 'chatroom.ai.provider.model' not in self.env:
            return credentials
        api_url, api_key, fallback_model = credentials
        selected_id = self.env['ir.config_parameter'].sudo().get_param('chatroom_whatsapp.ai_model_id')
        try:
            selected = self.env['chatroom.ai.provider.model'].sudo().browse(int(selected_id)).exists()
        except (TypeError, ValueError):
            selected = self.env['chatroom.ai.provider.model'].browse()
        if selected and selected.active and selected.supports_chat:
            return api_url, api_key, selected.model_id
        return api_url, api_key, fallback_model

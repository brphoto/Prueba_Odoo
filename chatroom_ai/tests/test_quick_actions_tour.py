# -*- coding: utf-8 -*-
"""Las acciones de IA en un navegador real (✨, atajos "/" y panel)."""
from unittest.mock import patch

from odoo.fields import Datetime
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestQuickActionsTour(HttpCase):

    def test_quick_actions_tour(self):
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('chatroom_whatsapp.ai_enabled', 'True')
        icp.set_param('chatroom_whatsapp.ai_provider_url', 'https://ia.invalid/v1')
        icp.set_param('chatroom_whatsapp.ai_api_key', 'clave-de-prueba')
        partner = self.env['res.partner'].create({'name': 'TOUR IA'})
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp', 'external_id': '573001119990',
            'partner_id': partner.id,
            'assigned_user_id': self.env.ref('base.user_admin').id,
            'last_message_date': Datetime.now(),
        })
        self.env['chatroom.message'].create({
            'channel_id': channel.id, 'direction': 'inbound', 'state': 'read',
            'body': 'Hola, quisiera información', 'date': Datetime.now(),
        })
        self.env.flush_all()
        # La IA se simula: el tour prueba la interfaz, no al proveedor.
        with patch.object(type(self.env['chatroom.channel']), '_ai_chat_completion',
                          return_value='Hola, ¿qué tal? Le cuento.'):
            self.start_tour(
                '/odoo/action-chatroom_whatsapp.action_chatroom_app',
                'chatroom_ai_quick_actions_tour', login='admin')

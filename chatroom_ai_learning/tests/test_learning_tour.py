# -*- coding: utf-8 -*-
"""El nivel de autonomía y el motivo del traspaso, en un navegador real."""
from odoo.fields import Datetime
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestLearningTour(HttpCase):

    def test_learning_tour(self):
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('chatroom_whatsapp.ai_enabled', 'True')
        icp.set_param('chatroom_whatsapp.ai_provider_url', 'https://ia.invalid/v1')
        icp.set_param('chatroom_whatsapp.ai_api_key', 'clave-de-prueba')
        icp.set_param('chatroom_ai_learning.autonomy_frozen', 'False')
        partner = self.env['res.partner'].create({'name': 'TOUR APRENDE'})
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp', 'external_id': '593990001234',
            'partner_id': partner.id, 'ai_intent': 'venta',
            'assigned_user_id': self.env.ref('base.user_admin').id,
            'last_message_date': Datetime.now(),
        })
        self.env['chatroom.message'].create({
            'channel_id': channel.id, 'direction': 'inbound', 'state': 'read',
            'body': 'Quiero hablar con una persona', 'date': Datetime.now(),
        })
        channel.write({'ai_paused': True, 'ai_pause_source': 'handoff',
                       'ai_handoff_reason': 'Pide un humano: el cliente mencionó «persona».'})
        self.env.ref('chatroom_ai_learning.level_venta').write({'state': 'supervised', 'locked': False})
        self.env.flush_all()
        self.start_tour('/odoo/action-chatroom_whatsapp.action_chatroom_app',
                        'chatroom_ai_learning_tour', login='admin')
        self.env.ref('chatroom_ai_learning.level_venta')._apply_rules()
        self.start_tour('/odoo/action-chatroom_ai_learning.action_ai_autonomy_level',
                        'chatroom_ai_learning_levels_tour', login='admin')

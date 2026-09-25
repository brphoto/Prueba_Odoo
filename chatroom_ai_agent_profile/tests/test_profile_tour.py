# -*- coding: utf-8 -*-
"""Perfil, probador y guion en un navegador real."""
import json
from unittest.mock import patch

from odoo.fields import Datetime
from odoo.tests import HttpCase, tagged

from .common import draft_json, fake_provider, setup_agent


@tagged('post_install', '-at_install')
class TestProfileTour(HttpCase):

    def test_profile_and_simulator_tour(self):
        setup_agent(self.env)
        self.env.flush_all()
        with patch.object(type(self.env['chatroom.channel']), '_ai_chat_completion', autospec=True,
                          side_effect=fake_provider(draft_json('Atendemos de lunes a viernes de 8:00 a 18:00.'))):
            self.start_tour('/odoo/action-chatroom_ai_agent_profile.action_agent_profile',
                            'chatroom_ai_agent_profile_tour', login='admin')

    def test_playbook_in_chat_tour(self):
        setup_agent(self.env)
        partner = self.env['res.partner'].create({'name': 'TOUR GUION'})
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp', 'external_id': '593990005678', 'partner_id': partner.id,
            'assigned_user_id': self.env.ref('base.user_admin').id, 'last_message_date': Datetime.now(),
            'ai_playbook_id': self.env.ref('chatroom_ai_agent_profile.playbook_quote').id,
            'ai_playbook_data': json.dumps({'necesidad': 'sillas', 'detalle': '3'}),
        })
        # Traspasada a otra asesora: se ve el ícono en la lista y se puede tomar.
        other = self.env['res.users'].create({'name': 'Otra Asesora', 'login': 'otra_asesora_tour',
                                              'group_ids': [(6, 0, [self.env.ref('base.group_user').id])]})
        channel.write({'ai_paused': True, 'ai_pause_source': 'handoff', 'ai_list_state': 'human',
                       'ai_handoff_reason': 'Guion completado', 'assigned_user_id': other.id})
        self.env['chatroom.message'].create({
            'channel_id': channel.id, 'direction': 'inbound', 'state': 'read',
            'body': 'Quiero cotizar 3 sillas', 'date': Datetime.now()})
        self.env.flush_all()
        self.start_tour('/odoo/action-chatroom_whatsapp.action_chatroom_app',
                        'chatroom_ai_agent_playbook_tour', login='admin')

    def test_inbox_tour(self):
        setup_agent(self.env)
        partner = self.env['res.partner'].create({'name': 'TOUR BANDEJA'})
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp', 'external_id': '593990009999', 'partner_id': partner.id,
            'last_message_date': Datetime.now()})
        self.env['chatroom.message'].create({'channel_id': channel.id, 'direction': 'inbound', 'state': 'read',
                                             'body': '¿Tienen sillas ergonómicas?', 'date': Datetime.now()})
        self.env['chatroom.ai.suggestion'].create_from_channel(channel, 'Sí, la Silla ergonómica Pro.')
        self.env.flush_all()
        with patch.object(type(self.env['chatroom.channel']), 'action_send_text', autospec=True, return_value=True):
            self.start_tour('/odoo/action-chatroom_ai_agent_profile.action_ai_inbox', 'chatroom_ai_inbox_tour',
                            login='admin')
        self.assertEqual(self.env['chatroom.ai.suggestion'].search([('channel_id', '=', channel.id)]).state, 'sent')

    def test_ai_center_tour(self):
        setup_agent(self.env)
        partner = self.env['res.partner'].create({'name': 'TOUR CENTRO'})
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp', 'external_id': '593990007777', 'partner_id': partner.id,
            'last_message_date': Datetime.now()})
        self.env['chatroom.message'].create({'channel_id': channel.id, 'direction': 'inbound', 'state': 'read',
                                             'body': '¿Arman los muebles?', 'date': Datetime.now()})
        suggestion = self.env['chatroom.ai.suggestion'].create_from_channel(channel, 'Sí, armamos los muebles.')
        self.env.flush_all()
        with patch.object(type(self.env['chatroom.channel']), 'action_send_text', autospec=True, return_value=True), \
                patch.object(type(self.env['chatroom.ai.service']), 'complete', autospec=True,
                             return_value='Lo más preguntado es el armado de los muebles.'):
            self.start_tour('/odoo/action-chatroom_ai_agent_profile.action_ai_center', 'chatroom_ai_center_tour',
                            login='admin')
        self.assertEqual(suggestion.state, 'sent')
        self.assertTrue(self.env['chatroom.ai.example'].search([('approved_text', 'ilike', 'armado es gratis')]),
                        'La corrección se aprendió.')
        profile = self.env.ref('chatroom_ai_agent_profile.profile_main')
        self.assertEqual(profile.autonomy_mode, 'prudent')
        self.assertTrue(self.env['ai.knowledge.base'].search([('source_text', 'ilike', 'Armamos los muebles gratis'),
                                                              ('publication_state', '=', 'published')]))

    def test_composer_draft_tour(self):
        setup_agent(self.env)
        partner = self.env['res.partner'].create({'name': 'TOUR BORRADOR'})
        channel = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp', 'external_id': '593990008888', 'partner_id': partner.id,
            'assigned_user_id': self.env.ref('base.user_admin').id, 'last_message_date': Datetime.now()})
        self.env['chatroom.message'].create({'channel_id': channel.id, 'direction': 'inbound', 'state': 'read',
                                             'body': '¿Envían a Cuenca?', 'date': Datetime.now()})
        suggestion = self.env['chatroom.ai.suggestion'].create_from_channel(channel, 'Sí, hacemos envíos a Cuenca.')
        channel.ai_list_state = 'draft'
        self.env.flush_all()
        self.start_tour('/odoo/action-chatroom_whatsapp.action_chatroom_app', 'chatroom_ai_composer_draft_tour',
                        login='admin')
        self.assertEqual(suggestion.state, 'rejected')

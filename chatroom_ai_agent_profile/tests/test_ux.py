# -*- coding: utf-8 -*-
"""Bandeja para aprobar, estado en la lista, tomar conversación, puesta en
marcha, escuchar la voz y tablero con tendencia y ahorro."""
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import TransactionCase, tagged

from .common import AgentMixin, draft_json, setup_agent


@tagged('post_install', '-at_install')
class TestAgentUx(AgentMixin, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.profile, cls.knowledge = setup_agent(cls.env)
        cls.agent = cls.env['res.users'].create({
            'name': 'Asesora UX', 'login': 'asesora_ux_test',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])]})
        cls.partner = cls.env['res.partner'].create({'name': 'Nora Vélez'})

    def _pending(self, text='¿Tienen sillas ergonómicas?', reply='Sí, tenemos varios modelos.'):
        channel = self._channel(text)
        with self._ai(draft_json(reply, backing='ninguno')), self._no_send():
            result = channel.action_ai_auto_reply_safe()
        return channel, self.env['chatroom.ai.suggestion'].browse(result['suggestion_id'])

    # ------------------------------------------------------------------
    # Bandeja «Para aprobar» y estado en la lista
    # ------------------------------------------------------------------
    def test_inbox_approve_edited_answer_learns_and_sends(self):
        channel, suggestion = self._pending()
        self.assertEqual(channel.ai_list_state, 'draft')
        self.assertEqual(suggestion.customer_question, '¿Tienen sillas ergonómicas?')
        self.assertGreaterEqual(suggestion.waiting_minutes, 0)
        inbox = self.env.ref('chatroom_ai_agent_profile.action_ai_inbox')
        self.assertIn(suggestion, self.env['chatroom.ai.suggestion'].search(eval(inbox.domain)))
        suggestion.suggested_text = 'Sí, la Silla ergonómica Pro cuesta 189 dólares.'
        with self._no_send() as sender:
            suggestion.action_approve_and_send()
        self.assertEqual(sender.call_args.args[1], 'Sí, la Silla ergonómica Pro cuesta 189 dólares.')
        self.assertEqual((suggestion.state, suggestion.feedback_state), ('sent', 'edited'))
        self.assertEqual(channel.ai_list_state, 'ai')
        example = self.env['chatroom.ai.example'].search([('approved_text', 'ilike', 'Silla ergonómica Pro cuesta')])
        self.assertEqual(example.ai_text, 'Sí, tenemos varios modelos.')

    def test_inbox_discard_and_open_chat(self):
        channel, suggestion = self._pending()
        action = suggestion.action_open_chat()
        self.assertEqual((action['tag'], action['params']['channel_id']), ('chatroom_whatsapp.chatroom_app', channel.id))
        suggestion.action_discard()
        self.assertEqual(suggestion.state, 'rejected')
        self.assertFalse(channel.ai_list_state)

    def test_list_state_follows_what_happened(self):
        with self._ai(draft_json('Atendemos de lunes a viernes de 8:00 a 18:00.')), self._no_send():
            answered = self._channel('¿Cuál es el horario de atención?')
            answered.action_ai_auto_reply_safe()
            handed = self._channel('Quiero hablar con una persona')
            handed.action_ai_auto_reply_safe()
        self.assertEqual((answered.ai_list_state, handed.ai_list_state), ('ai', 'human'))
        channel, _suggestion = self._pending()
        self.env['chatroom.message'].create({'channel_id': channel.id, 'direction': 'outbound', 'state': 'sent',
                                             'body': 'Hola, sí tenemos.', 'sender_user_id': self.agent.id})
        self.assertFalse(channel.ai_list_state, 'Respondió una persona: ya no hay borrador pendiente.')
        handed.ai_paused = False
        self.assertFalse(handed.ai_list_state)
        self.assertIn('ai_list_state', self.env['chatroom.channel']._fields)

    # ------------------------------------------------------------------
    # Tomar conversación
    # ------------------------------------------------------------------
    def test_take_over_assigns_pauses_and_closes_the_notice(self):
        channel = self._channel('Quiero hablar con una persona')  # asignada a otra asesora
        with self._ai('Resumen'), self._no_send():
            channel.action_ai_auto_reply_safe()
        self.assertTrue(channel.get_ai_assistant_data()['can_take_over'])
        notices = self.env['chatroom.notification'].search([('channel_id', '=', channel.id)])             if 'chatroom.notification' in self.env else False
        self.assertTrue(notices or channel.activity_ids, 'El traspaso avisa (notificación o actividad).')
        result = channel.action_ai_take_over()
        self.assertEqual(channel.assigned_user_id, self.env.user)
        self.assertTrue(channel.ai_paused)
        self.assertEqual((channel.ai_pause_source, channel.ai_list_state), ('human', 'human'))
        self.assertFalse(channel.activity_ids, 'El aviso de traspaso queda resuelto.')
        if notices:
            self.assertEqual(set(notices.mapped('state')), {'done'})
        self.assertFalse(result['can_take_over'])
        self.assertIn('tomó la conversación', self.env['mail.message'].search(
            [('model', '=', 'chatroom.channel'), ('res_id', '=', channel.id)], limit=1).body)

    def test_handoff_notice_shows_collected_data(self):
        channel = self._channel('Quiero cotizar 3 sillas ergonómicas', intent='venta')
        with self._ai(draft_json('Gracias, el equipo continúa.', intent='venta', backing='guion', playbook='cotizacion',
                                 data={'nombre': 'Nora Vélez', 'necesidad': 'sillas ergonómicas', 'detalle': '3'})), \
                self._no_send():
            channel.action_ai_auto_reply_safe()
        collected = channel.get_ai_assistant_data()['playbook']['collected']
        self.assertIn({'label': 'Producto o servicio que necesita', 'value': 'sillas ergonómicas'}, collected)

    # ------------------------------------------------------------------
    # Puesta en marcha y voz
    # ------------------------------------------------------------------
    def test_setup_wizard_takes_a_business_from_zero_to_ready(self):
        wizard = self.env['chatroom.ai.agent.setup'].create({'profile_id': self.profile.id})
        self.assertEqual(wizard.step, 'company')
        wizard.write({'business_description': '', 'agent_name': 'Lía'})
        with self.assertRaises(Exception):
            wizard.action_next()
        wizard.write({'business_description': 'Somos una pastelería en Cuenca; hacemos tortas por encargo y '
                                              'entregamos a domicilio.', 'company_name': 'Dulce Hogar'})
        wizard.action_next()
        self.assertEqual((wizard.step, self.profile.agent_name, self.env.company.name),
                         ('knowledge', 'Lía', 'Dulce Hogar'))
        wizard.knowledge_text = 'Tortas por encargo con 48 horas de anticipación.\n\nEntregas en Cuenca: 3 dólares.'
        wizard.action_next()
        knowledge = self.env['ai.knowledge.base'].search([('name', '=', 'Información general (puesta en marcha)')])
        self.assertEqual((knowledge.state, knowledge.publication_state), ('indexed', 'published'))
        wizard.write({'use_support': False, 'quote_action': 'quote'})
        wizard.action_next()
        self.assertEqual(wizard.step, 'launch')
        self.assertFalse(self.env.ref('chatroom_ai_agent_profile.playbook_support').active)
        self.assertEqual(self.env.ref('chatroom_ai_agent_profile.playbook_quote').on_complete, 'quote')
        self.assertEqual(wizard.action_test()['res_model'], 'chatroom.ai.agent.simulator')
        wizard.action_activate()
        self.assertEqual(self.env['ir.config_parameter'].sudo().get_param('chatroom_whatsapp.ai_auto_reply'), 'True')
        wizard.action_back()
        self.assertEqual(wizard.step, 'playbooks')

    def test_listen_to_the_voice(self):
        self.profile.voice_replies = 'audio'
        with patch.object(type(self.env['chatroom.channel']), '_ai_speech', return_value=b'OggS') as speech:
            action = self.profile.action_preview_voice()
        self.assertIn('Soy Valeria', speech.call_args.args[0].replace('soy', 'Soy'))
        attachment = self.env['ir.attachment'].browse(int(action['url'].split('/')[3].split('?')[0]))
        self.assertEqual((action['type'], attachment.raw, attachment.mimetype),
                         ('ir.actions.act_url', b'OggS', 'audio/ogg'))

    # ------------------------------------------------------------------
    # Tablero
    # ------------------------------------------------------------------
    def test_dashboard_weekly_trend_and_savings(self):
        Event = self.env['chatroom.ai.agent.event']
        today = fields.Date.context_today(self.profile)
        for days_ago, kind, cached, cost in ((1, 'sent', False, 0.002), (1, 'sent', True, 0.0),
                                             (1, 'approval', False, 0.002), (8, 'sent', False, 0.002),
                                             (8, 'handoff', False, 0.0)):
            Event.create({'kind': kind, 'cached': cached, 'cost': cost, 'tokens': 0 if cached else 2000,
                          'profile_id': self.profile.id, 'date': today - timedelta(days=days_ago)})
        values = self.profile._dashboard_values()
        trend = values['trend']
        self.assertEqual(len(trend), 8)
        self.assertEqual(sum(week['total'] for week in trend), 5)
        self.assertAlmostEqual(values['savings']['reused_usd'], 0.002)
        self.assertEqual(values['savings']['reused_tokens'], 2000)
        self.assertIn('Ahorro estimado', self.profile.dashboard_html)
        self.assertIn('Respondió sola por semana', self.profile.dashboard_html)

# -*- coding: utf-8 -*-
"""Búsqueda en el conocimiento, tablero, acciones de guion, seguimiento,
aprendizaje desde chats anteriores y ráfagas de mensajes."""
import json
from datetime import timedelta
from unittest.mock import MagicMock, patch

from odoo import fields
from odoo.tests import TransactionCase, tagged

from .common import AgentMixin, draft_json, setup_agent

SEARCH = 'odoo.addons.chatroom_ai_agent_profile.models.knowledge_search.requests.post'


def fake_embeddings(vocabulary):
    """Vectores por tema: cada texto apunta al tema de la primera palabra que contiene."""
    def post(url, headers=None, json=None, timeout=None):
        vectors = []
        for text in json['input']:
            lowered = text.lower()
            vector = [0.0] * len(vocabulary)
            for index, words in enumerate(vocabulary):
                if any(word in lowered for word in words):
                    vector[index] = 1.0
            vectors.append(vector if any(vector) else [0.01] * len(vocabulary))
        response = MagicMock(status_code=200)
        response.json.return_value = {'data': [{'index': i, 'embedding': v} for i, v in enumerate(vectors)]}
        return response
    return post


@tagged('post_install', '-at_install')
class TestAgentOps(AgentMixin, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.profile, cls.knowledge = setup_agent(cls.env)
        cls.profile.semantic_search = False
        cls.agent = cls.env['res.users'].create({
            'name': 'Asesor Ops', 'login': 'asesor_ops_test',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])]})
        cls.partner = cls.env['res.partner'].create({'name': 'Lucía Paz'})
        cls.KB = cls.env['ai.knowledge.base']

    def _context(self, query):
        return self.KB.get_sales_context_details(False, query=query)['context']

    # ------------------------------------------------------------------
    # Búsqueda en el conocimiento
    # ------------------------------------------------------------------
    def test_synonyms_plurals_and_accents(self):
        self.assertIn('25 dólares', self._context('¿Cuál es el costo del plan básico?'))
        self.assertIn('48 horas', self._context('hacen envios a Loja?'))
        self.profile.synonyms = ''
        self.assertNotIn('25 dólares', self._context('¿Cuál es el costo?'))

    def test_semantic_search_finds_meaning_without_shared_words(self):
        self.env['ir.config_parameter'].sudo().set_param('chatroom_ai_agent_profile.embeddings_failed_at', '')
        self.profile.semantic_search = True
        vocabulary = [('horario', 'abren', 'atendemos', 'hora'), ('envío', 'envíos', 'llega'), ('plan', 'cuesta')]
        with patch(SEARCH, side_effect=fake_embeddings(vocabulary)):
            self.knowledge._embed_chunks()
            self.assertEqual(len(self.knowledge.chunk_ids), 3)
            self.assertTrue(self.knowledge.semantic_ready)
            # «¿a qué hora abren?» no comparte palabras con «Horario de atención: lunes a viernes...».
            self.profile.synonyms = ''
            context = self._context('¿a qué hora abren mañana?')
        self.assertIn('lunes a viernes', context)

    def test_audio_transcript_is_used_to_search_knowledge(self):
        """Con IA real, un audio respondía «no tengo información»: se buscaba con el texto vacío."""
        channel = self._channel('')
        channel.message_ids.write({'message_type': 'audio', 'body': False,
                                   'ai_transcript': 'Quería saber cuánto demoran los envíos a Loja'})
        system = channel._ai_build_conversation(extra_system=channel._ai_guarded_draft_prompt())[0]['content']
        self.assertIn('48 horas', system)

    def test_semantic_failure_falls_back_to_keywords(self):
        self.env['ir.config_parameter'].sudo().set_param('chatroom_ai_agent_profile.embeddings_failed_at', '')
        self.profile.semantic_search = True
        with patch(SEARCH, side_effect=RuntimeError('sin embeddings')):
            self.knowledge._embed_chunks()
            self.assertIn('25 dólares', self._context('precio del plan básico'))
        self.assertTrue(self.env['ir.config_parameter'].sudo().get_param(
            'chatroom_ai_agent_profile.embeddings_failed_at'))
        self.assertFalse(self.KB._semantic_enabled(), 'No insiste durante una hora.')

    # ------------------------------------------------------------------
    # Tablero
    # ------------------------------------------------------------------
    def test_every_reply_is_logged_for_the_dashboard(self):
        Event = self.env['chatroom.ai.agent.event']
        with self._ai(draft_json('Atendemos de lunes a viernes de 8:00 a 18:00.')), self._no_send():
            sent = self._channel('¿Cuál es el horario de atención?')
            sent.action_ai_auto_reply_safe()
            local = self._channel('Hola')
            local.action_ai_auto_reply_safe()
            handoff = self._channel('Quiero hablar con una persona')
            handoff.action_ai_auto_reply_safe()
        kinds = {event.channel_id: event.kind for event in Event.search([])}
        self.assertEqual((kinds[sent], kinds[local], kinds[handoff]), ('sent', 'local', 'handoff'))
        self.assertGreaterEqual(Event.search([('channel_id', '=', sent.id)]).latency_ms, 0)
        values = self.profile._dashboard_values()
        self.assertEqual(values['answered'], 3)
        self.assertAlmostEqual(values['alone_rate'], 200.0 / 3, places=1)
        self.assertIn('Respondió sola', self.profile.dashboard_html)

    # ------------------------------------------------------------------
    # Guiones que terminan en una acción
    # ------------------------------------------------------------------
    def test_completed_playbook_prepares_a_draft_quote(self):
        quote = self.env.ref('chatroom_ai_agent_profile.playbook_quote')
        quote.on_complete = 'quote'
        self.env['product.product'].create({'name': 'Silla ergonómica Pro', 'list_price': 189.0, 'sale_ok': True})
        self.env['product.product'].create({'name': 'Cojín para silla', 'list_price': 12.0, 'sale_ok': True})
        channel = self._channel('Quiero cotizar 3 sillas ergonómicas, soy Lucía Paz', intent='venta')
        with self._ai(draft_json('Gracias Lucía, el equipo te enviará la cotización.', intent='venta', backing='guion',
                                 playbook='cotizacion', data={'nombre': 'Lucía Paz', 'necesidad': 'sillas ergonómicas',
                                                              'detalle': '3 sillas'})), self._no_send():
            result = channel.action_ai_auto_reply_safe()
        self.assertEqual(result['status'], 'handoff')
        if 'sale.order' in self.env:
            order = self.env['sale.order'].search([('partner_id', '=', self.partner.id)], limit=1)
            self.assertTrue(order, 'Cotización en borrador creada.')
            self.assertEqual(order.state, 'draft')
            self.assertEqual(order.order_line.product_uom_qty, 3)
            self.assertEqual(order.order_line.product_id.name, 'Silla ergonómica Pro',
                             'Solo el producto que mejor coincide, no el «Cojín para silla».')
        else:
            self.assertTrue(channel.activity_ids)

    def test_customer_always_gets_a_closing_message(self):
        """Con IA real el cierre quedó para aprobar y el cliente no recibió nada."""
        channel = self._channel('Quiero cotizar 3 sillas ergonómicas, soy Lucía Paz', intent='venta')
        with self._ai(draft_json('Tu cotización ya está lista y aprobada.', intent='venta', backing='conocimiento',
                                 playbook='cotizacion', data={'nombre': 'Lucía Paz', 'necesidad': 'sillas',
                                                              'detalle': '3'}), verified=False),                 self._no_send() as sender:
            result = channel.action_ai_auto_reply_safe()
        self.assertEqual((result['status'], result['reply_status']), ('handoff', 'sent_fallback'))
        self.assertIn('continúa contigo', sender.call_args.args[1])

    def test_completed_playbook_can_create_a_task(self):
        self.env.ref('chatroom_ai_agent_profile.playbook_support').on_complete = 'activity'
        channel = self._channel('El pedido 5521 llegó con una pata rota', intent='soporte')
        with self._ai(draft_json('Gracias, lo reviso con el equipo.', intent='soporte', backing='guion',
                                 playbook='soporte', data={'referencia': '5521', 'problema': 'pata rota'})), \
                self._no_send():
            channel.action_ai_auto_reply_safe()
        self.assertEqual(channel.activity_ids.user_id, self.agent)
        self.assertIn('pata rota', channel.activity_ids.note)

    # ------------------------------------------------------------------
    # Seguimiento
    # ------------------------------------------------------------------
    def test_followup_once_for_a_stalled_playbook(self):
        channel = self._channel('Quiero cotizar sillas')
        channel.write({'ai_playbook_id': self.env.ref('chatroom_ai_agent_profile.playbook_quote').id,
                       'ai_playbook_data': json.dumps({'necesidad': 'sillas'}),
                       'last_message_date': fields.Datetime.now()})
        question = self.env['chatroom.message'].create({
            'channel_id': channel.id, 'direction': 'outbound', 'body': '¿Cuántas necesitas?', 'state': 'sent',
            'ai_generated': True})
        question.date = fields.Datetime.now() - timedelta(hours=5)
        with self._no_send() as sender:
            self.assertEqual(self.env['chatroom.channel']._cron_ai_followups(), 1)
            self.assertEqual(self.env['chatroom.channel']._cron_ai_followups(), 0, 'Solo una vez.')
        text = sender.call_args.args[1]
        self.assertIn('Lucía', text)
        self.assertIn('cotización o compra', text)
        self.assertIn('nombre del cliente', text)
        self.assertTrue(self.env['chatroom.ai.agent.event'].search([('channel_id', '=', channel.id),
                                                                    ('kind', '=', 'followup')]))

    # ------------------------------------------------------------------
    # Aprender de chats anteriores
    # ------------------------------------------------------------------
    def test_history_import_learns_examples_faq_and_cases(self):
        channel = self._channel('Hola, ¿hacen factura electrónica para empresas?')
        channel.last_message_date = fields.Datetime.now()
        self.env['chatroom.message'].create({
            'channel_id': channel.id, 'direction': 'outbound', 'state': 'sent', 'sender_user_id': self.agent.id,
            'body': 'Sí, emitimos factura electrónica; necesitamos RUC, razón social y correo.'})
        faq = json.dumps({'faq': [{'pregunta': '¿Emiten factura electrónica?',
                                   'respuesta': 'Sí, con RUC, razón social y correo.', 'veces': 4}]})
        wizard = self.env['chatroom.ai.history.import'].create({'profile_id': self.profile.id})
        with self._ai(faq):
            wizard.action_run()
        self.assertEqual(wizard.state, 'done')
        self.assertTrue(self.env['chatroom.ai.example'].search([('source', '=', 'history')]))
        gap = self.env['chatroom.ai.knowledge.gap'].search([('source', '=', 'history')])
        self.assertEqual((gap.state, gap.count), ('proposed', 4))
        self.assertTrue(self.env['chatroom.ai.eval.case'].search([('name', '=', '¿Emiten factura electrónica?')]))
        gap.action_publish()
        self.assertIn('razón social', self._context('factura electronica'))

    # ------------------------------------------------------------------
    # Ráfagas y sensibilidad del traspaso
    # ------------------------------------------------------------------
    def test_burst_is_read_as_a_whole(self):
        channel = self._channel('Me cobraron dos veces el pedido')
        self._inbound(channel, 'hola?')
        with self._ai(draft_json('Hola')), self._no_send():
            result = channel.action_ai_auto_reply_safe()
        self.assertEqual(result['status'], 'handoff', 'El reclamo del primer mensaje cuenta.')
        channel = self._channel('Hola')
        self._inbound(channel, '¿cuál es el horario?')
        self.assertFalse(channel._ai_local_reply(), '«Hola» + pregunta lo responde la IA.')

    def test_upset_customer_rule_can_require_urgency(self):
        rule = self.env.ref('chatroom_ai_learning.rule_upset')
        Rules = self.env['chatroom.ai.handoff.rule']
        draft = {'sentiment': 'negative', 'urgency': 'normal', 'confidence': 0.9}
        self.assertEqual(Rules._match_draft(draft)[0], rule)
        rule.negative_requires_urgency = True
        self.assertFalse(Rules._match_draft(draft)[0] == rule)
        self.assertEqual(Rules._match_draft(dict(draft, urgency='high'))[0].trigger, 'negative')

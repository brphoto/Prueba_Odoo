# -*- coding: utf-8 -*-
"""Agente que opera solo: traspaso, autonomía por niveles, modo sombra,
aprendizaje de correcciones, memoria y pruebas de regresión.

La IA siempre se simula: se prueba la lógica de decisión, no al proveedor.
"""
import json
from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import TransactionCase, tagged


def draft_json(reply, confidence=0.95, intent='consulta', needs_human=False,
               sentiment='neutral', urgency='normal', reason='ok'):
    return json.dumps({'reply': reply, 'confidence': confidence, 'intent': intent,
                       'needs_human': needs_human, 'sentiment': sentiment,
                       'urgency': urgency, 'reason': reason})


@tagged('post_install', '-at_install')
class TestAiLearning(TransactionCase):
    _seq = 0

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        icp = cls.env['ir.config_parameter'].sudo()
        for key, value in {
            'chatroom_whatsapp.ai_enabled': 'True',
            'chatroom_whatsapp.ai_provider_url': 'https://ia.invalid/v1',
            'chatroom_whatsapp.ai_api_key': 'clave-de-prueba',
            'chatroom_whatsapp.business_hours_enabled': 'False',
            'chatroom_ai_agent.safe_auto_reply': 'True',
            'chatroom_ai_agent.require_approval': 'True',
            'chatroom_whatsapp.ai_require_approval': 'True',
            'chatroom_ai_learning.shadow_rate': '100',
            'chatroom_ai_learning.autonomy_frozen': 'False',
            'chatroom_ai_learning.min_samples': '5',
        }.items():
            icp.set_param(key, value)
        # Una política de chatroom_ai_autonomy (si está instalada) no debe
        # interferir: aquí se prueba la autonomía por niveles.
        if 'chatroom.ai.autonomy.policy' in cls.env:
            cls.env['chatroom.ai.autonomy.policy'].search([]).write({'active': False})
        cls.agent = cls.env['res.users'].create({
            'name': 'Asesora Aprende', 'login': 'asesora_aprende_test',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
        })
        cls.partner = cls.env['res.partner'].create({'name': 'Cliente Aprende'})
        cls.Channel = cls.env['chatroom.channel']
        cls.Level = cls.env['chatroom.ai.autonomy.level']
        cls.Evaluation = cls.env['chatroom.ai.evaluation']

    def _channel(self, text, intent=False):
        TestAiLearning._seq += 1
        channel = self.Channel.create({
            'channel_type': 'whatsapp', 'external_id': '59309900%04d' % TestAiLearning._seq,
            'partner_id': self.partner.id, 'assigned_user_id': self.agent.id, 'ai_intent': intent,
        })
        self._inbound(channel, text)
        return channel

    def _inbound(self, channel, text):
        return self.env['chatroom.message'].create({
            'channel_id': channel.id, 'direction': 'inbound', 'body': text, 'state': 'read'})

    def _human_reply(self, channel, text):
        return self.env['chatroom.message'].create({
            'channel_id': channel.id, 'direction': 'outbound', 'body': text, 'state': 'sent',
            'sender_user_id': self.agent.id})

    @contextmanager
    def _ai(self, answer):
        """Simula al proveedor. `answer` es texto o una función(conversation)."""
        def fake(_self, conversation, *args, **kwargs):
            return answer(conversation) if callable(answer) else answer
        with patch.object(type(self.Channel), '_ai_chat_completion', fake):
            yield

    @contextmanager
    def _no_send(self):
        with patch.object(type(self.Channel), 'action_send_text', autospec=True,
                          return_value=True) as sender:
            yield sender

    # ------------------------------------------------------------------
    # Traspaso a una persona
    # ------------------------------------------------------------------
    def test_keyword_handoff_pauses_notifies_and_warns_customer(self):
        channel = self._channel('Hola, quiero hablar con una persona por favor')
        rule = self.env.ref('chatroom_ai_learning.rule_ask_human')
        with self._ai('El cliente pide atención humana.'), self._no_send() as sender:
            result = channel.action_ai_auto_reply_safe()
        self.assertEqual(result['status'], 'handoff')
        self.assertTrue(channel.ai_paused)
        self.assertEqual(channel.ai_pause_source, 'handoff')
        self.assertIn(rule.name, channel.ai_handoff_reason)
        self.assertEqual(rule.match_count, 1)
        sender.assert_called_once()
        self.assertEqual(sender.call_args.args[1], rule.customer_message)
        note = self.env['mail.message'].search([
            ('model', '=', 'chatroom.channel'), ('res_id', '=', channel.id)], order='id desc', limit=1)
        self.assertIn('Traspaso a una persona', note.body)
        self.assertIn('El cliente pide atención humana.', note.body)
        if 'chatroom.notification' in self.env:
            self.assertTrue(self.env['chatroom.notification'].search([
                ('channel_id', '=', channel.id), ('user_id', '=', self.agent.id)]))
        # Ya pausada, la IA no vuelve a responder.
        self.assertEqual(channel.action_ai_auto_reply_safe()['status'], 'human_active')

    def test_draft_rule_handoff_for_upset_customer(self):
        channel = self._channel('Llevo tres días esperando y nadie me responde')
        with self._ai(draft_json('Lamento la demora.', sentiment='negative', intent='soporte')), \
                self._no_send():
            result = channel.action_ai_auto_reply_safe()
        self.assertEqual(result['status'], 'handoff')
        self.assertEqual(result['rule'], self.env.ref('chatroom_ai_learning.rule_upset').name)
        self.assertTrue(channel.ai_paused)

    def test_handoff_disabled_keeps_normal_flow(self):
        self.env['ir.config_parameter'].sudo().set_param('chatroom_ai_learning.handoff_enabled', 'False')
        channel = self._channel('quiero hablar con una persona')
        with self._ai(draft_json('Claro, te ayudo.')), self._no_send():
            result = channel.action_ai_auto_reply_safe()
        self.assertNotEqual(result['status'], 'handoff')
        self.assertFalse(channel.ai_paused)

    # ------------------------------------------------------------------
    # Autonomía por niveles
    # ------------------------------------------------------------------
    def test_supervised_level_waits_for_approval(self):
        channel = self._channel('¿Qué cubre el seguro de auto?')
        with self._ai(draft_json('Cubre daños propios y a terceros.')), self._no_send() as sender:
            result = channel.action_ai_auto_reply_safe()
        self.assertEqual(result['status'], 'awaiting_approval')
        sender.assert_not_called()

    def test_automatic_level_replies_alone_even_with_global_approval(self):
        self.env.ref('chatroom_ai_learning.level_consulta').action_set_automatic()
        channel = self._channel('¿Qué cubre el seguro de auto?')
        with self._ai(draft_json('Cubre daños propios y a terceros.')), self._no_send() as sender:
            result = channel.action_ai_auto_reply_safe()
        self.assertEqual(result['status'], 'sent')
        sender.assert_called_once()

    def test_frozen_autonomy_and_blocked_level_need_a_person(self):
        self.env.ref('chatroom_ai_learning.level_consulta').action_set_automatic()
        self.env['ir.config_parameter'].sudo().set_param('chatroom_ai_learning.autonomy_frozen', 'True')
        channel = self._channel('¿Qué cubre el seguro de auto?')
        with self._ai(draft_json('Cubre daños propios.')), self._no_send() as sender:
            result = channel.action_ai_auto_reply_safe()
        self.assertEqual(result['status'], 'human_review')
        self.assertIn('congelada', result['reason'])
        sender.assert_not_called()

        self.env['ir.config_parameter'].sudo().set_param('chatroom_ai_learning.autonomy_frozen', 'False')
        self.env['chatroom.ai.handoff.rule'].search([('trigger', '=', 'intent')]).active = False
        channel = self._channel('Tengo una observación sobre el trámite')
        with self._ai(draft_json('Gracias, lo revisamos.', intent='queja')), self._no_send() as sender:
            result = channel.action_ai_auto_reply_safe()
        self.assertEqual(result['status'], 'human_review')
        sender.assert_not_called()

    def test_level_promotes_with_data_and_demotes_on_unsafe(self):
        level = self.env.ref('chatroom_ai_learning.level_soporte')
        level.locked = False
        for index in range(5):
            self.Evaluation.create({'source': 'feedback', 'category': 'soporte', 'verdict': 'good',
                                    'ai_text': 'respuesta %s' % index})
        level._apply_rules()
        self.assertEqual(level.state, 'automatic')
        self.assertEqual(level.success_rate, 100.0)
        # Una sola respuesta insegura la devuelve a supervisado al instante.
        self.Evaluation.create({'source': 'feedback', 'category': 'soporte', 'verdict': 'unsafe'})
        self.assertEqual(level.state, 'supervised')
        self.assertEqual(level.unsafe_count, 1)

    def test_level_does_not_promote_with_few_or_bad_samples(self):
        level = self.env.ref('chatroom_ai_learning.level_venta')
        for verdict in ('good', 'good', 'bad', 'bad', 'good'):
            self.Evaluation.create({'source': 'feedback', 'category': 'venta', 'verdict': verdict})
        level._apply_rules()
        self.assertEqual(level.state, 'supervised')
        self.assertEqual(level.success_rate, 60.0)
        self.assertIn('necesita', level.status_note)

    def test_locked_level_ignores_metrics(self):
        level = self.env.ref('chatroom_ai_learning.level_soporte')
        level.action_set_supervised()
        for _index in range(6):
            self.Evaluation.create({'source': 'feedback', 'category': 'soporte', 'verdict': 'good'})
        level._apply_rules()
        self.assertEqual(level.state, 'supervised')
        level.action_unlock()
        self.assertEqual(level.state, 'automatic')

    # ------------------------------------------------------------------
    # Aprender del equipo
    # ------------------------------------------------------------------
    def test_shadow_mode_compares_blind_draft_with_human_reply(self):
        channel = self._channel('¿Hasta qué hora atienden?', intent='consulta')
        self._human_reply(channel, 'Atendemos de lunes a viernes de 8:00 a 18:00.')
        evaluation = self.Evaluation.search([('channel_id', '=', channel.id)])
        self.assertEqual((evaluation.source, evaluation.state), ('shadow', 'pending'))

        seen = []

        def provider(conversation):
            seen.append(conversation)
            return draft_json('Atendemos de lunes a viernes de 8:00 a 18:00.')
        with self._ai(provider):
            self.Evaluation._cron_process_shadow()
        self.assertEqual((evaluation.state, evaluation.verdict), ('done', 'good'))
        # La IA no vio la respuesta humana que se usa para calificarla.
        self.assertFalse(any('8:00 a 18:00' in turn['content'] for turn in seen[0] if turn['role'] != 'system'))
        # Nada se envió al cliente: el modo sombra es silencioso.
        self.assertFalse(channel.message_ids.filtered('ai_generated'))

    def test_shadow_wrong_answer_is_learned_as_example(self):
        channel = self._channel('¿Aceptan pago con transferencia?', intent='consulta')
        self._human_reply(channel, 'Sí, aceptamos transferencia al Banco Pichincha.')

        def provider(conversation):
            if 'Evalúas respuestas' in conversation[0]['content']:
                return json.dumps({'veredicto': 'incorrecta', 'motivo': 'Dijo que no.'})
            return draft_json('No, solo efectivo.')
        with self._ai(provider):
            self.Evaluation._cron_process_shadow()
        evaluation = self.Evaluation.search([('channel_id', '=', channel.id)])
        self.assertEqual(evaluation.verdict, 'bad')
        self.assertTrue(evaluation.example_id)
        self.assertEqual(evaluation.example_id.approved_text, 'Sí, aceptamos transferencia al Banco Pichincha.')

        # La próxima vez la IA recibe la respuesta del equipo como ejemplo.
        other = self._channel('Hola, ¿aceptan pago con transferencia bancaria?', intent='consulta')
        conversation = other._ai_build_conversation()
        self.assertIn('Banco Pichincha', conversation[0]['content'])

    def test_shadow_escalation_is_not_counted_as_success(self):
        channel = self._channel('Necesito ayuda con algo', intent='soporte')
        self._human_reply(channel, 'Claro, cuéntame.')
        with self._ai(draft_json('', needs_human=True)):
            self.Evaluation._cron_process_shadow()
        evaluation = self.Evaluation.search([('channel_id', '=', channel.id)])
        self.assertEqual(evaluation.verdict, 'escalated')

    def test_used_draft_is_evaluated_and_corrections_learned(self):
        channel = self._channel('¿Tienen seguro de vida?', intent='venta')
        self.env['chatroom.ai.suggestion'].create_from_channel(
            channel, 'Sí, tenemos seguro de vida desde 10 dólares.')
        self._human_reply(channel, 'Sí, tenemos seguro de vida. ¿Para cuántas personas lo necesitas?')
        evaluation = self.Evaluation.search([('channel_id', '=', channel.id)])
        self.assertEqual(evaluation.source, 'suggestion')
        self.assertIn(evaluation.verdict, ('acceptable', 'bad'))
        self.assertIn('cuántas personas', evaluation.example_id.approved_text)

    def test_unsafe_feedback_pauses_and_demotes(self):
        level = self.env.ref('chatroom_ai_learning.level_consulta')
        level.write({'state': 'automatic', 'locked': False})
        channel = self._channel('¿Me devuelven el dinero?', intent='consulta')
        suggestion = self.env['chatroom.ai.suggestion'].create_from_channel(channel, 'Sí, seguro.')
        suggestion._set_feedback('unsafe')
        self.assertTrue(channel.ai_paused)
        self.assertEqual(channel.ai_pause_source, 'unsafe')
        self.assertEqual(level.state, 'supervised')
        self.assertTrue(self.Evaluation.search([('suggestion_id', '=', suggestion.id), ('verdict', '=', 'unsafe')]))

    # ------------------------------------------------------------------
    # Reactivación y memoria
    # ------------------------------------------------------------------
    def test_ai_resumes_after_human_answered_and_silence(self):
        old = fields.Datetime.now() - timedelta(hours=13)
        answered = self._channel('Hola')
        self.env['chatroom.message'].create({'channel_id': answered.id, 'direction': 'outbound',
                                             'body': 'Listo, resuelto.', 'state': 'sent'})
        waiting = self._channel('Hola')
        unsafe = self._channel('Hola')
        self.env['chatroom.message'].create({'channel_id': unsafe.id, 'direction': 'outbound',
                                             'body': 'Revisamos.', 'state': 'sent'})
        (answered | waiting).write({'ai_paused': True})
        unsafe.write({'ai_paused': True, 'ai_pause_source': 'unsafe'})
        (answered | waiting | unsafe).write({'last_message_date': old})
        self.assertEqual(answered.ai_pause_source, 'human')
        self.Channel._cron_resume_ai()
        self.assertFalse(answered.ai_paused)
        self.assertFalse(answered.ai_pause_source)
        self.assertTrue(waiting.ai_paused, 'El cliente espera respuesta: sigue la persona.')
        self.assertTrue(unsafe.ai_paused, 'Tras una respuesta insegura no se reactiva sola.')

    def test_memory_needs_consent_and_low_confidence_goes_to_review(self):
        channel = self._channel('Mi carro es un Kia Sportage 2022 y prefiero que me escriban en la tarde')
        facts = json.dumps({'hechos': [
            {'titulo': 'Vehículo', 'contenido': 'Tiene un Kia Sportage 2022.', 'tipo': 'fact', 'confianza': 0.95},
            {'titulo': 'Horario', 'contenido': 'Prefiere mensajes en la tarde.', 'tipo': 'preference',
             'confianza': 0.6},
        ]})
        Memory = self.env['chatroom.ai.memory'].with_context(active_test=False)
        has_consent_model = 'ec.data.consent' in self.env
        if has_consent_model:
            with self._ai(facts), patch.object(type(self.env['ec.data.consent']), 'has_active_consent',
                                               return_value=False):
                self.assertEqual(channel._ai_extract_memories(), 0)
            self.assertFalse(Memory.search([('partner_id', '=', self.partner.id)]))
            consent = patch.object(type(self.env['ec.data.consent']), 'has_active_consent', return_value=True)
        else:
            consent = patch.object(type(self.Channel), '_ai_memory_consent_ok', return_value=True)
        with self._ai(facts), consent:
            self.assertEqual(channel._ai_extract_memories(), 2)
        memories = Memory.search([('partner_id', '=', self.partner.id)])
        approved = memories.filtered(lambda memory: memory.review_state == 'approved')
        pending = memories.filtered(lambda memory: memory.review_state == 'pending')
        self.assertEqual(approved.content, 'Tiene un Kia Sportage 2022.')
        self.assertTrue(approved.active)
        self.assertFalse(pending.active)
        pending.action_approve_memory()
        self.assertTrue(pending.active)
        # No se duplican datos ya sabidos.
        with self._ai(facts), consent:
            self.assertEqual(channel._ai_extract_memories(), 0)

    # ------------------------------------------------------------------
    # Pruebas de regresión que congelan la autonomía
    # ------------------------------------------------------------------
    def test_regression_run_freezes_and_releases_autonomy(self):
        Run = self.env['chatroom.ai.eval.run']
        icp = self.env['ir.config_parameter'].sudo()
        with self._ai(draft_json('El precio es 300 dólares al año.', intent='venta')):
            run = Run.run_all()
        self.assertTrue(run.froze_autonomy)
        self.assertEqual(icp.get_param('chatroom_ai_learning.autonomy_frozen'), 'True')
        failed = run.result_ids.filtered(lambda result: not result.passed)
        self.assertEqual(failed.case_id, self.env.ref('chatroom_ai_learning.case_no_invented_price'))

        self.env.ref('chatroom_ai_learning.level_venta').action_set_automatic()
        self.assertFalse(self.env.ref('chatroom_ai_learning.level_venta').allows_automatic())

        with self._ai(draft_json('Con gusto te cotizo. ¿Qué marca, modelo y año es tu carro?',
                                 intent='venta')):
            run = Run.run_all()
        self.assertEqual(run.pass_rate, 100.0)
        self.assertFalse(run.froze_autonomy)
        self.assertEqual(icp.get_param('chatroom_ai_learning.autonomy_frozen'), 'False')
        self.assertTrue(self.env.ref('chatroom_ai_learning.level_venta').allows_automatic())

    def test_evaluation_becomes_regression_case(self):
        evaluation = self.Evaluation.create({
            'source': 'feedback', 'category': 'consulta', 'verdict': 'escalated',
            'customer_message': 'Quiero cancelar mi póliza'})
        action = evaluation.action_create_test_case()
        case = self.env['chatroom.ai.eval.case'].browse(action['res_id'])
        self.assertEqual(case.expected, 'handoff')
        self.assertEqual(case._conversation(), [{'role': 'user', 'content': 'Quiero cancelar mi póliza'}])

    def test_assistant_data_shows_level_and_handoff(self):
        channel = self._channel('quiero hablar con una persona')
        with self._ai('Resumen'), self._no_send():
            channel.action_ai_auto_reply_safe()
        data = channel.get_ai_assistant_data()
        self.assertEqual(data['autonomy_level']['state'], 'supervised')
        self.assertIn('persona', data['handoff_reason'])

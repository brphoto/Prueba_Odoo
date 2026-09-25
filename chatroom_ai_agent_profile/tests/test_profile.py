# -*- coding: utf-8 -*-
"""Agente configurable que responde bien desde el inicio.

La IA se simula: se prueba lo que se le envía y lo que se decide con su
respuesta, igual en producción, casos de prueba y probador.
"""
import json

from odoo.tests import TransactionCase, tagged

from .common import AgentMixin, KNOWLEDGE, draft_json, is_verifier, setup_agent, verifier_json


@tagged('post_install', '-at_install')
class TestAgentProfile(AgentMixin, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.profile, cls.knowledge = setup_agent(cls.env)
        cls.agent = cls.env['res.users'].create({
            'name': 'Asesor Perfil', 'login': 'asesor_perfil_test',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
        })
        cls.partner = cls.env['res.partner'].create({'name': 'Carla Mena'})
        cls.Gap = cls.env['chatroom.ai.knowledge.gap']

    # ------------------------------------------------------------------
    # Instrucciones
    # ------------------------------------------------------------------
    def test_prompt_has_identity_rules_playbooks_and_knowledge(self):
        channel = self._channel('Hola, ¿cuál es el horario de atención?')
        with self._ai(draft_json('Atendemos de lunes a viernes de 8:00 a 18:00.')) as seen, self._no_send():
            channel.action_ai_auto_reply_safe()
        system = seen[0][0]['content']
        self.assertIn('Eres Valeria, asesor de atención al cliente', system)
        self.assertIn('muebles de oficina', system)
        self.assertIn('No inventes precios', system)
        self.assertIn('[cotizacion] Cotización o compra', system)
        self.assertIn('"respaldo"', system)
        self.assertIn('lunes a viernes de 8:00 a 18:00', system)
        self.assertIn('Cliente: Carla Mena', system)

    def test_line_profile_overrides_general_one(self):
        line = self.env['chatroom.whatsapp.number'].create({
            'name': 'Línea mayoristas', 'phone_number_id': '5930001112223'})
        own = self.env['chatroom.ai.agent.profile'].create({
            'name': 'Mayoristas', 'agent_name': 'Diego', 'line_ids': [(6, 0, line.ids)]})
        Profile = self.env['chatroom.ai.agent.profile']
        self.assertEqual(Profile._for_line(line), own)
        self.assertEqual(Profile._for_line(None), self.profile)

    def test_quick_replies_are_generic_and_configurable(self):
        channel = self._channel('Hola')
        self.assertEqual(channel._ai_local_reply(),
                         'Hola Carla, soy Valeria de %s. ¿En qué te puedo ayudar?' % self.env.company.name)
        channel = self._channel('muchas gracias!')
        self.assertEqual(channel._ai_local_reply(), 'Con gusto. Aquí estamos para lo que necesites.')
        # Nada de textos fijos de otro negocio: lo demás lo responde la IA.
        channel = self._channel('cuales son sus servicios')
        self.assertFalse(channel._ai_local_reply())

    # ------------------------------------------------------------------
    # Arranque: responde bien desde el primer día
    # ------------------------------------------------------------------
    def test_backed_answer_is_sent_from_day_one(self):
        channel = self._channel('¿Cuál es el horario de atención?')
        with self._ai(draft_json('Atendemos de lunes a viernes de 8:00 a 18:00.')), self._no_send() as sender:
            result = channel.action_ai_auto_reply_safe()
        self.assertEqual(result['status'], 'sent')
        sender.assert_called_once()
        suggestion = self.env['chatroom.ai.suggestion'].browse(result['suggestion_id'])
        self.assertIn('Arranque con conocimiento', suggestion.safety_reason)

    def test_invented_figures_wait_for_approval(self):
        channel = self._channel('¿Cuánto cuesta el plan básico?')
        with self._ai(draft_json('El plan básico cuesta 30 dólares mensuales.')), self._no_send() as sender:
            result = channel.action_ai_auto_reply_safe()
        self.assertEqual(result['status'], 'awaiting_approval')
        sender.assert_not_called()
        with self._ai(draft_json('El plan básico cuesta 25 dólares mensuales.')), self._no_send() as sender:
            result = self._channel('¿Cuánto cuesta el plan básico?').action_ai_auto_reply_safe()
        self.assertEqual(result['status'], 'sent')

    def test_unbacked_or_disabled_bootstrap_waits_for_approval(self):
        channel = self._channel('¿Tienen sillas ergonómicas?')
        with self._ai(draft_json('Sí, tenemos varios modelos.', backing='ninguno')), self._no_send() as sender:
            self.assertEqual(channel.action_ai_auto_reply_safe()['status'], 'awaiting_approval')
        sender.assert_not_called()
        self.profile.bootstrap_autonomy = False
        channel = self._channel('¿Cuál es el horario de atención?')
        with self._ai(draft_json('Atendemos de lunes a viernes de 8:00 a 18:00.')), self._no_send() as sender:
            self.assertEqual(channel.action_ai_auto_reply_safe()['status'], 'awaiting_approval')
        sender.assert_not_called()

    def test_bootstrap_respects_frozen_and_manual_levels(self):
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('chatroom_ai_learning.autonomy_frozen', 'True')
        with self._ai(draft_json('Atendemos de lunes a viernes de 8:00 a 18:00.')), self._no_send() as sender:
            result = self._channel('¿Horario?').action_ai_auto_reply_safe()
        self.assertEqual(result['status'], 'awaiting_approval')
        sender.assert_not_called()
        icp.set_param('chatroom_ai_learning.autonomy_frozen', 'False')
        self.env.ref('chatroom_ai_learning.level_consulta').action_set_supervised()
        with self._ai(draft_json('Atendemos de lunes a viernes de 8:00 a 18:00.')), self._no_send() as sender:
            result = self._channel('¿Horario?').action_ai_auto_reply_safe()
        self.assertEqual(result['status'], 'awaiting_approval')

    # ------------------------------------------------------------------
    # Guiones
    # ------------------------------------------------------------------
    def test_playbook_collects_data_and_hands_off_when_complete(self):
        channel = self._channel('Quiero cotizar 3 sillas ergonómicas', intent='venta')
        with self._ai(draft_json('Con gusto. ¿A nombre de quién preparo la cotización?', intent='venta',
                                 backing='guion', playbook='cotizacion',
                                 data={'necesidad': 'sillas ergonómicas', 'detalle': '3 unidades',
                                       'inventado': 'x'})), self._no_send() as sender:
            result = channel.action_ai_auto_reply_safe()
        self.assertEqual(result['status'], 'sent')
        sender.assert_called_once()
        self.assertEqual(channel.ai_playbook_id, self.env.ref('chatroom_ai_agent_profile.playbook_quote'))
        self.assertEqual(json.loads(channel.ai_playbook_data),
                         {'necesidad': 'sillas ergonómicas', 'detalle': '3 unidades'})
        self.assertFalse(channel.ai_playbook_done)
        progress = channel.get_ai_assistant_data()['playbook']
        self.assertEqual((progress['filled'], progress['total']), (2, 3))
        self.assertEqual(progress['missing'], ['Nombre del cliente'])

        self._inbound(channel, 'Soy Carla Mena')
        seen_prompt = []

        def provider(conversation):
            if is_verifier(conversation):
                return verifier_json(True)
            seen_prompt.append(conversation[0]['content'])
            return draft_json('Gracias Carla. Un asesor te enviará la cotización en breve.', intent='venta',
                              backing='guion', playbook='cotizacion', data={'nombre': 'Carla Mena'})
        with self._ai(provider), self._no_send() as sender:
            result = channel.action_ai_auto_reply_safe()
        self.assertIn('Datos ya obtenidos', seen_prompt[0])
        self.assertIn('sillas ergonómicas', seen_prompt[0])
        self.assertEqual(result['status'], 'handoff')
        self.assertEqual(result['reply_status'], 'sent')
        sender.assert_called_once()
        self.assertTrue(channel.ai_playbook_done)
        self.assertTrue(channel.ai_paused)
        note = self.env['mail.message'].search([('model', '=', 'chatroom.channel'), ('res_id', '=', channel.id),
                                                ('body', 'ilike', 'Nombre del cliente')], limit=1)
        self.assertIn('Nombre del cliente: Carla Mena', note.body)

    def test_playbook_code_variants_keep_collected_data(self):
        """Con IA real el modelo devolvió «[cotizacion]»: los datos no deben perderse."""
        Playbook = self.env['chatroom.ai.agent.playbook']
        playbooks = self.profile.playbook_ids
        quote = self.env.ref('chatroom_ai_agent_profile.playbook_quote')
        for code in ('[cotizacion]', 'Cotización', ' COTIZACION '):
            chosen, data, _done, _new = Playbook._advance(
                playbooks, Playbook, {}, False, {'playbook_code': code, 'collected': {'necesidad': 'sillas'}})
            self.assertEqual((chosen, data), (quote, {'necesidad': 'sillas'}), code)
        # Código desconocido con un guion en curso: los datos se suman a ese guion.
        chosen, data, _done, _new = Playbook._advance(
            playbooks, quote, {'necesidad': 'sillas'}, False,
            {'playbook_code': 'cotizar_sillas', 'collected': {'detalle': '3'}})
        self.assertEqual((chosen, data), (quote, {'necesidad': 'sillas', 'detalle': '3'}))

    def test_invented_playbook_data_is_ignored(self):
        """Con IA real el modelo anotó «nombre: cliente» sin que el cliente lo dijera."""
        Playbook = self.env['chatroom.ai.agent.playbook']
        quote = self.env.ref('chatroom_ai_agent_profile.playbook_quote')
        chosen, data, done, newly = Playbook._advance(
            self.profile.playbook_ids, Playbook, {}, False,
            {'playbook_code': 'cotizacion', 'evidence': 'Hola, quiero cotizar 3 escritorios',
             'collected': {'nombre': 'cliente', 'necesidad': 'escritorios', 'detalle': '3'}})
        self.assertEqual(chosen, quote)
        self.assertEqual(data, {'necesidad': 'escritorios', 'detalle': '3'})
        self.assertFalse(done or newly)
        # El nombre que ya conoce Odoo sí cuenta.
        _chosen, data, done, _newly = Playbook._advance(
            self.profile.playbook_ids, quote, data, False,
            {'playbook_code': 'cotizacion', 'evidence': 'Quiero cotizar Carla Mena',
             'collected': {'nombre': 'Carla Mena'}})
        self.assertTrue(done)

    def test_playbook_codes_and_keys_are_generated(self):
        playbook = self.env['chatroom.ai.agent.playbook'].create({
            'profile_id': self.profile.id, 'name': 'Reserva de mesa', 'when_to_use': 'Cuando quiere reservar.',
            'field_ids': [(0, 0, {'label': 'Número de personas'}), (0, 0, {'label': 'Fecha y hora'})]})
        self.assertEqual(playbook.code, 'reserva_de_mesa')
        self.assertEqual(playbook.field_ids.mapped('key'), ['numero_de_personas', 'fecha_y_hora'])

    # ------------------------------------------------------------------
    # Vacíos: la base de conocimiento crece sola
    # ------------------------------------------------------------------
    def test_knowledge_gap_is_captured_answered_and_published(self):
        channel = self._channel('¿Aceptan pagos con criptomonedas?')
        with self._ai(draft_json('Lo consulto con el equipo y te confirmo.', confidence=0.4, needs_human=True,
                                 backing='ninguno', gap='¿Aceptan pagos con criptomonedas?')), self._no_send():
            result = channel.action_ai_auto_reply_safe()
        self.assertEqual(result['status'], 'human_review')
        gap = self.Gap.search([('channel_id', '=', channel.id)])
        self.assertEqual((gap.state, gap.count), ('open', 1))

        # Lo que responde el equipo queda como respuesta propuesta.
        self.env['chatroom.message'].create({
            'channel_id': channel.id, 'direction': 'outbound', 'state': 'sent',
            'body': 'Por ahora no; aceptamos transferencia y tarjeta.', 'sender_user_id': self.agent.id})
        self.assertEqual(gap.state, 'proposed')
        self.assertIn('transferencia', gap.answer)

        # Otra pregunta parecida suma al mismo vacío.
        self.Gap._register_question('Hola, ¿ustedes aceptan pagos con criptomonedas?', channel=channel)
        self.assertEqual(gap.count, 2)

        gap.action_publish()
        self.assertEqual(gap.state, 'published')
        self.assertEqual(gap.knowledge_id.publication_state, 'published')
        context = self.env['ai.knowledge.base'].get_sales_context_details(False, query='criptomonedas')
        self.assertIn('aceptamos transferencia y tarjeta', context['context'])

    # ------------------------------------------------------------------
    # Probador y casos de prueba: mismo proceso que producción
    # ------------------------------------------------------------------
    def _simulator(self):
        return self.env['chatroom.ai.agent.simulator'].create({'profile_id': self.profile.id})

    def test_simulator_matches_production(self):
        simulator = self._simulator()
        answer = draft_json('Atendemos de lunes a viernes de 8:00 a 18:00.')
        with self._ai(answer) as seen, self._no_send():
            simulator.message = '¿Cuál es el horario de atención?'
            simulator.action_send()
            production = self._channel('¿Cuál es el horario de atención?').action_ai_auto_reply_safe()
        self.assertEqual((simulator.last_decision, production['status']), ('send', 'sent'))
        self.assertIn('Eres Valeria', seen[0][0]['content'])
        self.assertIn('lunes a viernes', seen[0][0]['content'])
        self.assertIn('Información general', simulator.last_sources)
        self.assertIn('lunes a viernes', simulator.chat_html)

        answer = draft_json('El plan cuesta 99 dólares.')
        with self._ai(answer), self._no_send():
            simulator.message = '¿Cuánto cuesta el plan?'
            simulator.action_send()
            production = self._channel('¿Cuánto cuesta el plan?').action_ai_auto_reply_safe()
        self.assertEqual((simulator.last_decision, production['status']), ('approval', 'awaiting_approval'))

    def test_simulator_quick_reply_handoff_playbook_and_learning(self):
        simulator = self._simulator()
        with self._ai('no debería llamarse'):
            simulator.message = 'Hola'
            simulator.action_send()
        self.assertEqual(simulator.last_decision, 'local')

        simulator.message = 'quiero hablar con una persona'
        simulator.action_send()
        self.assertEqual(simulator.last_decision, 'handoff')

        simulator.action_reset()
        with self._ai(draft_json('¿Cuántas sillas necesitas?', intent='venta', backing='guion',
                                 playbook='cotizacion', data={'necesidad': 'sillas'})):
            simulator.message = 'Quiero cotizar sillas'
            simulator.action_send()
        self.assertEqual(simulator.playbook_id.code, 'cotizacion')
        self.assertIn('1/3', simulator.playbook_progress)

        simulator.correction = 'Claro, ¿cuántas sillas y para qué ciudad?'
        simulator.action_correct()
        example = self.env['chatroom.ai.example'].search([
            ('approved_text', '=', 'Claro, ¿cuántas sillas y para qué ciudad?')])
        self.assertTrue(example)

        action = simulator.action_save_case()
        case = self.env['chatroom.ai.eval.case'].browse(action['res_id'])
        self.assertEqual(case.expected, 'reply')
        self.assertEqual(case.transcript, 'Cliente: Quiero cotizar sillas')
        self.assertIn('cuántas sillas', case.reference_answer)

    def test_regression_cases_use_profile_and_knowledge(self):
        case = self.env['chatroom.ai.eval.case'].create({
            'name': 'Horario', 'transcript': 'Cliente: ¿Cuál es el horario de atención?',
            'expected': 'reply', 'must_include': 'lunes'})
        with self._ai(draft_json('Atendemos de lunes a viernes de 8:00 a 18:00.')) as seen:
            passed, detail, _answer = case._evaluate()
        self.assertTrue(passed, detail)
        system = seen[0][0]['content']
        self.assertIn('Eres Valeria', system)
        self.assertIn('Horario de atención: lunes a viernes', system)

    # ------------------------------------------------------------------
    # Lo encontrado probando con la IA real
    # ------------------------------------------------------------------
    def test_verifier_blocks_deduced_answers(self):
        """El modelo dice «conocimiento» aunque haya deducido: el verificador lo frena."""
        channel = self._channel('Si armo el escritorio yo mismo, ¿pierdo la garantía?')
        with self._ai(draft_json('No, no pierdes la garantía.'), verified=False) as seen, \
                self._no_send() as sender:
            result = channel.action_ai_auto_reply_safe()
        self.assertEqual(result['status'], 'awaiting_approval')
        sender.assert_not_called()
        self.assertTrue(any(is_verifier(conversation) for conversation in seen))
        suggestion = self.env['chatroom.ai.suggestion'].browse(result['suggestion_id'])
        self.assertTrue(suggestion)
        # Sin verificador (opción apagada) no hay segunda consulta.
        self.profile.verify_before_send = False
        with self._ai(draft_json('Atendemos de lunes a viernes de 8:00 a 18:00.')) as seen, self._no_send():
            result = self._channel('¿Horario?').action_ai_auto_reply_safe()
        self.assertEqual(result['status'], 'sent')
        self.assertFalse(any(is_verifier(conversation) for conversation in seen))

    def test_plain_text_reply_is_retried_as_json(self):
        """Con historial el modelo a veces contesta en texto normal: se le pide el JSON de nuevo."""
        answers = iter(['Perfecto, ¿a nombre de quién?', draft_json('¿A nombre de quién preparo la cotización?',
                                                                   backing='guion', intent='venta')])

        def provider(conversation):
            if is_verifier(conversation):
                return verifier_json(True)
            reminders = [turn['content'] for turn in conversation[1:] if turn['role'] == 'system']
            self.assertTrue(any('responde SOLO con el JSON' in text for text in reminders))
            return next(answers)
        channel = self._channel('Quiero cotizar escritorios', intent='venta')
        with self._ai(provider), self._no_send():
            result = channel.action_ai_auto_reply_safe()
        self.assertEqual(result['status'], 'sent')

    def test_gap_detected_from_reply_text(self):
        simulator = self.env['chatroom.ai.agent.simulator'].create({'profile_id': self.profile.id})
        with self._ai(draft_json('No tengo información sobre descuentos por volumen; lo consulto con el equipo.',
                                 backing='ninguno', confidence=0.8)):
            simulator.message = 'Si compro 10 sillas, ¿me hacen descuento?'
            simulator.action_send()
        self.assertEqual(simulator.last_gap, 'Si compro 10 sillas, ¿me hacen descuento?')
        self.assertEqual(simulator.last_decision, 'approval')

    def test_questions_only_replies_are_low_risk(self):
        from odoo.addons.chatroom_ai_agent_profile.models.chatroom import only_asks, unsupported_numbers
        self.assertTrue(only_asks('¿Cuál es tu nombre?'))
        self.assertTrue(only_asks('Perfecto, necesito tu nombre y tu ciudad.'))
        self.assertFalse(only_asks('No hacemos envíos a Galápagos.'))
        self.assertFalse(only_asks('Ya dejé listo tu pedido.'))
        self.assertFalse(only_asks('¿Me confirmas? El envío es gratis.'))
        self.assertEqual(unsupported_numbers('Cuesta $189', 'precio 189.00 USD'), set())
        self.assertEqual(unsupported_numbers('Cuesta 30 dólares', 'cuesta 25 dólares'), {'30'})
        # El modelo la marcó «ninguno», pero solo pide un dato del guion: se envía.
        channel = self._channel('Quiero cotizar escritorios', intent='venta')
        with self._ai(draft_json('¿Cuántos escritorios necesitas?', intent='venta', backing='ninguno',
                                 playbook='cotizacion', data={'necesidad': 'escritorios'})) as seen, \
                self._no_send() as sender:
            result = channel.action_ai_auto_reply_safe()
        self.assertEqual(result['status'], 'sent')
        sender.assert_called_once()
        self.assertFalse(any(is_verifier(conversation) for conversation in seen),
                         'Una respuesta que solo pregunta no necesita verificador.')

    def test_small_catalog_and_customer_language_in_prompt(self):
        self.env['product.template'].create({'name': 'Silla ergonómica Pro', 'list_price': 189.0, 'sale_ok': True})
        channel = self._channel('¿Qué me recomiendas para trabajar sentado muchas horas?')
        with self._ai(draft_json('Te recomiendo la Silla ergonómica Pro, cuesta $189.')) as seen, \
                self._no_send() as sender:
            result = channel.action_ai_auto_reply_safe()
        system = seen[0][0]['content']
        if self.env['product.template'].search_count([('sale_ok', '=', True)]) <= 30:
            self.assertIn('Silla ergonómica Pro: 189.00', system)
            # «$189» está respaldado por «189.00» del catálogo.
            self.assertEqual(result['status'], 'sent')
            sender.assert_called_once()
        self.assertIn('idioma en que escribe el cliente', system)

    # ------------------------------------------------------------------
    # Preparación
    # ------------------------------------------------------------------
    def test_readiness_and_enable_auto_reply(self):
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('chatroom_whatsapp.ai_auto_reply', 'False')
        self.profile.invalidate_recordset()
        self.assertFalse(self.profile.is_ready)
        self.assertIn('Respuesta automática activada', self.profile.readiness_html)
        self.profile.action_enable_auto_reply()
        self.profile.invalidate_recordset()
        self.assertEqual(icp.get_param('chatroom_whatsapp.ai_auto_reply'), 'True')
        self.assertTrue(self.profile.is_ready)
        self.assertIn('Eres Valeria', self.profile.prompt_preview)
        self.assertIn(KNOWLEDGE[:20], self.knowledge.content_text)

# -*- coding: utf-8 -*-
"""Acciones rápidas de IA: catálogo configurable, contexto por acción,
resultado por modo, visibilidad y métricas de calidad."""
from unittest.mock import patch

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger


@tagged('post_install', '-at_install')
class TestQuickActions(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Ana Cliente', 'phone': '+593990001000'})
        cls.line = cls.env['chatroom.whatsapp.number'].create({
            'name': 'Tienda Norte', 'phone_number_id': 'PNID-QA-NORTE',
            'ai_persona': 'Eres el asistente de Tienda Norte y tuteas al cliente.',
        })
        cls.channel = cls.env['chatroom.channel'].create({
            'channel_type': 'whatsapp', 'external_id': '593990001000',
            'partner_id': cls.partner.id, 'whatsapp_number_id': cls.line.id,
        })
        cls.env['chatroom.message'].create({
            'channel_id': cls.channel.id, 'direction': 'inbound',
            'message_type': 'text', 'body': 'Hola, ¿cuánto cuesta la silla ergonómica?',
        })
        cls.Action = cls.env['chatroom.ai.quick.action']

    def _action(self, **values):
        base = {'name': 'Acción QA', 'instruction': 'Responde a {cliente} desde {linea}.',
                'company_id': False}
        base.update(values)
        return self.Action.create(base)

    def _run(self, action, reply='Texto IA', **kwargs):
        captured = {}

        def fake(channel, messages, task_type=None, model_id=None):
            captured.update(messages=messages, task_type=task_type, model_id=model_id)
            return reply

        with patch.object(type(self.channel), '_ai_chat_completion', fake):
            result = self.channel.action_ai_run_quick_action(action.id, **kwargs)
        return result, captured

    # -- Catálogo -------------------------------------------------------

    def test_seeded_actions_replace_the_three_fixed_options(self):
        shortcuts = {action['shortcut'] for action in self.channel.get_ai_quick_actions()}
        for shortcut in ('responder', 'mejorar', 'precio', 'resumen', 'intencion', 'traducir'):
            self.assertIn(shortcut, shortcuts)

    def test_panel_data_includes_actions_and_config_flag(self):
        data = self.channel.get_ai_assistant_data()
        self.assertTrue(data['quick_actions'])
        self.assertIn('can_configure', data)

    def test_shortcut_must_be_a_single_lowercase_word(self):
        with self.assertRaises(ValidationError):
            self._action(shortcut='Con Espacios')

    def test_shortcut_is_unique_among_active_actions(self):
        self._action(shortcut='unico_qa')
        with mute_logger('odoo.sql_db'), self.assertRaises(Exception), self.env.cr.savepoint():
            self._action(shortcut='unico_qa')
        archived = self._action(shortcut='otro_qa', active=False)
        self._action(shortcut='otro_qa')
        self.assertFalse(archived.active)

    # -- Instrucción y contexto -----------------------------------------

    def test_variables_tone_and_language_reach_the_prompt(self):
        action = self._action(tone='formal', language='en', max_words=30)
        _result, captured = self._run(action)
        system = captured['messages'][0]['content']
        self.assertIn('Responde a Ana Cliente desde Tienda Norte.', system)
        self.assertIn('tratando de usted', system)
        self.assertIn('Responde en inglés', system)
        self.assertIn('30 palabras', system)

    def test_line_persona_is_added_to_every_ai_call(self):
        action = self._action()
        _result, captured = self._run(action)
        self.assertIn('Tienda Norte y tuteas', captured['messages'][0]['content'])

    def test_catalog_source_adds_live_products(self):
        if 'product.product' not in self.env:
            self.skipTest('Sin productos instalados.')
        self.env['product.product'].create({
            'name': 'Silla ergonómica QA', 'list_price': 120.0, 'sale_ok': True})
        # Sin base de conocimiento, que ya trae productos por su cuenta: así se
        # ve solo el efecto de la casilla de catálogo.
        _result, captured = self._run(self._action(use_catalog=True, use_knowledge=False))
        system = captured['messages'][0]['content']
        self.assertIn('Catálogo relacionado', system)
        self.assertIn('Silla ergonómica QA', system)
        _result, captured = self._run(self._action(use_catalog=False, use_knowledge=False))
        self.assertNotIn('Silla ergonómica QA', captured['messages'][0]['content'])

    def test_knowledge_and_memory_can_be_turned_off(self):
        action = self._action(use_knowledge=False, use_memory=False)
        with patch.object(type(self.channel), '_ai_line_persona', return_value=''):
            _result, captured = self._run(action)
        system = captured['messages'][0]['content']
        self.assertNotIn('Manuales internos autorizados', system)
        self.assertNotIn('Memoria empresarial autorizada', system)

    # -- Resultado por modo ---------------------------------------------

    def test_reply_creates_an_auditable_draft_linked_to_the_action(self):
        action = self._action(output_mode='reply')
        result, captured = self._run(action, reply='Cuesta 120 USD.')
        self.assertEqual(result['mode'], 'reply')
        suggestion = self.env['chatroom.ai.suggestion'].browse(result['suggestion']['id'])
        self.assertEqual(suggestion.state, 'draft')
        self.assertEqual(suggestion.quick_action_id, action)
        self.assertEqual(captured['task_type'], 'reply')
        self.assertEqual(action.use_count, 1)

    def test_rewrite_uses_the_draft_and_requires_one(self):
        action = self._action(output_mode='rewrite', instruction='Mejora el borrador.')
        with self.assertRaisesRegex(UserError, 'borrador'):
            self._run(action)
        result, captured = self._run(action, reply='Hola Ana, con gusto.', draft_text='hola ana con gusto')
        self.assertEqual(result, {'mode': 'rewrite', 'text': 'Hola Ana, con gusto.'})
        self.assertIn('hola ana con gusto', captured['messages'][-1]['content'])

    def test_note_is_posted_inside_the_conversation(self):
        action = self._action(output_mode='note', name='Traspaso QA')
        result, _captured = self._run(action, reply='- Pidió precio de silla')
        self.assertEqual(result['mode'], 'note')
        notes = ' '.join(note['body'] for note in self.channel.get_internal_notes())
        self.assertIn('Traspaso QA: - Pidió precio de silla', notes)

    def test_summary_and_intent_update_the_conversation(self):
        result, captured = self._run(self._action(output_mode='summary'), reply='Quiere precio.')
        self.assertEqual(result['summary'], 'Quiere precio.')
        self.assertEqual(self.channel.ai_summary, 'Quiere precio.')
        self.assertEqual(captured['task_type'], 'summary')
        result, captured = self._run(self._action(output_mode='intent'), reply='{"intent": "venta"}')
        self.assertEqual(result['intent'], 'venta')
        self.assertEqual(self.channel.ai_intent, 'venta')
        self.assertEqual(captured['task_type'], 'classification')
        result, _captured = self._run(self._action(output_mode='intent'), reply='Diría que es una queja.')
        self.assertEqual(result['intent'], 'queja')

    def test_paused_ai_blocks_customer_facing_actions_only(self):
        self.channel.ai_paused = True
        with self.assertRaisesRegex(UserError, 'pausada'):
            self._run(self._action(output_mode='reply'))
        result, _captured = self._run(self._action(output_mode='summary'), reply='ok')
        self.assertEqual(result['mode'], 'summary')

    # -- Visibilidad ----------------------------------------------------

    def test_actions_can_be_restricted_to_lines_and_groups(self):
        other_line = self.env['chatroom.whatsapp.number'].create({
            'name': 'Otra', 'phone_number_id': 'PNID-QA-OTRA'})
        only_other = self._action(name='Solo otra línea', line_ids=[(6, 0, other_line.ids)])
        only_here = self._action(name='Solo esta línea', line_ids=[(6, 0, self.line.ids)])
        ids = {a['id'] for a in self.channel.get_ai_quick_actions()}
        self.assertIn(only_here.id, ids)
        self.assertNotIn(only_other.id, ids)
        with self.assertRaisesRegex(UserError, 'no está disponible'):
            self._run(only_other)

        agent = new_test_user(self.env, login='agente_qa_acciones',
                              groups='chatroom_whatsapp.group_chatroom_user')
        managers_only = self._action(
            name='Solo administradores',
            group_ids=[(6, 0, self.env.ref('chatroom_whatsapp.group_chatroom_manager').ids)])
        self.channel.assigned_user_id = agent
        ids = {a['id'] for a in self.channel.with_user(agent).get_ai_quick_actions()}
        self.assertNotIn(managers_only.id, ids)
        self.assertIn(only_here.id, ids)

    # -- Calidad --------------------------------------------------------

    def test_quality_rates_come_from_human_feedback(self):
        action = self._action(output_mode='reply')
        Suggestion = self.env['chatroom.ai.suggestion']
        for feedback in ('helpful', 'helpful', 'edited', 'unsafe'):
            suggestion = Suggestion.create_from_channel(self.channel, 'Texto')
            suggestion.write({'quick_action_id': action.id, 'feedback_state': feedback})
        action.invalidate_recordset()
        self.assertEqual(action.suggestion_count, 4)
        self.assertEqual(action.helpful_count, 2)
        self.assertAlmostEqual(action.helpful_rate, 50.0)
        self.assertAlmostEqual(action.edit_rate, 25.0)
        self.assertEqual(action.action_view_suggestions()['domain'], [('quick_action_id', '=', action.id)])

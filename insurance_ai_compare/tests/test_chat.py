# -*- coding: utf-8 -*-
"""Asesoría de seguros desde el chat: /perfil, /faltantes y /comparativo."""
import json
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import new_test_user, tagged

from .common import InsuranceCompareCase


@tagged('post_install', '-at_install')
class TestInsuranceChat(InsuranceCompareCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.channel = cls.env['chatroom.channel'].create({
            'channel_type': 'whatsapp', 'external_id': '593990007000', 'partner_id': cls.partner.id,
        })
        for body, direction in (
                ('Hola, quiero asegurar mi carro, es un Kia Rio 2022', 'inbound'),
                ('Claro, ¿para qué lo usa?', 'outbound'),
                ('Para ir al trabajo en Quito, lo que más me importa es tener auto de reemplazo', 'inbound')):
            cls.env['chatroom.message'].create({
                'channel_id': cls.channel.id, 'direction': direction,
                'message_type': 'text', 'body': body,
            })

    def _run(self, xmlid, ai_answer=None, captured=None, **kwargs):
        action = self.env.ref(xmlid)

        def fake_complete(service, messages, task_type='document', model_id=None, timeout=120):
            if captured is not None:
                captured.append(messages)
            return json.dumps(ai_answer)

        def fake_chat(channel, messages, task_type=None, model_id=None):
            if captured is not None:
                captured.append(messages)
            return 'Respuesta de prueba'

        with patch.object(type(self.env['chatroom.ai.service']), 'complete', fake_complete), \
                patch.object(type(self.env['chatroom.channel']), '_ai_chat_completion', fake_chat):
            return self.channel.action_ai_run_quick_action(action.id, **kwargs)

    def test_profile_is_built_from_the_conversation(self):
        captured = []
        result = self._run('insurance_ai_compare.quick_action_insurance_profile', {
            'datos': {'marca': 'Kia', 'modelo': 'Rio', 'anio': 2022, 'uso': 'trabajo',
                      'ciudad': 'Quito', 'inventado': 'no debe guardarse'},
            'prioridades': 'Auto de reemplazo', 'resumen': 'Kia Rio 2022 para trabajo en Quito.',
        }, captured=captured)
        self.assertEqual(result['mode'], 'note')
        transcript = captured[0][-1]['content']
        self.assertIn('Cliente: Hola, quiero asegurar mi carro', transcript)
        self.assertIn('Asesor: Claro', transcript)
        profile = self.env['insurance.client.profile'].browse(result['profile_id'])
        data = profile._data()
        self.assertEqual(data['marca'], 'Kia')
        self.assertNotIn('inventado', data, 'Solo se guardan los datos definidos en la plantilla.')
        self.assertEqual(profile.priorities, 'Auto de reemplazo')
        self.assertIn('Valor comercial', profile.missing_fields)
        self.assertLess(profile.completion, 100)
        notes = ' '.join(note['body'] for note in self.channel.get_internal_notes())
        self.assertIn('Faltan:', notes)

        # Un segundo /perfil agrega datos sin borrar los anteriores.
        self._run('insurance_ai_compare.quick_action_insurance_profile', {
            'datos': {'marca': None, 'valor_comercial': 18500}})
        self.assertEqual(profile._data()['marca'], 'Kia')
        self.assertEqual(profile._data()['valor_comercial'], 18500)

    def test_missing_data_message_uses_the_checklist(self):
        self._run('insurance_ai_compare.quick_action_insurance_profile', {
            'datos': {'marca': 'Kia', 'modelo': 'Rio'}})
        captured = []
        result = self._run('insurance_ai_compare.quick_action_insurance_missing', captured=captured)
        self.assertEqual(result['mode'], 'reply')
        system = captured[0][0]['content']
        self.assertIn('Datos que todavía faltan', system)
        self.assertIn('Año del vehículo', system)
        self.assertIn('Marca del vehículo: Kia', system)

    def test_compare_is_created_from_the_chat_with_the_profile(self):
        self._run('insurance_ai_compare.quick_action_insurance_profile', {
            'datos': {'marca': 'Kia'}, 'prioridades': 'Precio bajo'})
        result = self._run('insurance_ai_compare.quick_action_insurance_compare')
        self.assertEqual(result['mode'], 'action')
        compare = self.env['insurance.compare'].browse(result['compare_id'])
        self.assertEqual(compare.partner_id, self.partner)
        self.assertEqual(compare.channel_id, self.channel)
        self.assertTrue(compare.profile_id)
        self.assertEqual(compare.priorities, 'Precio bajo')
        self.assertEqual(result['action']['res_id'], compare.id)

    def test_chat_actions_need_consent(self):
        stranger = self.env['res.partner'].create({'name': 'Sin consentimiento chat QA'})
        self.channel.partner_id = stranger
        with self.assertRaisesRegex(UserError, 'LOPDP'):
            self._run('insurance_ai_compare.quick_action_insurance_profile', {'datos': {}})
        with self.assertRaisesRegex(UserError, 'LOPDP'):
            self._run('insurance_ai_compare.quick_action_insurance_missing')

    def test_insurance_actions_are_only_for_advisors(self):
        agent = new_test_user(self.env, login='agente_sin_seguros_qa',
                              groups='chatroom_whatsapp.group_chatroom_user')
        advisor = new_test_user(
            self.env, login='agente_asesor_qa',
            groups='chatroom_whatsapp.group_chatroom_user,insurance_ai_compare.group_insurance_compare_user')
        self.channel.assigned_user_id = agent
        shortcuts = {a['shortcut'] for a in self.channel.with_user(agent).get_ai_quick_actions()}
        self.assertNotIn('perfil', shortcuts)
        self.channel.assigned_user_id = advisor
        shortcuts = {a['shortcut'] for a in self.channel.with_user(advisor).get_ai_quick_actions()}
        self.assertTrue({'perfil', 'faltantes', 'asesorar', 'explicar', 'comparativo'} <= shortcuts)

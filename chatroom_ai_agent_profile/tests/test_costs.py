# -*- coding: utf-8 -*-
"""Ahorro de IA y respuestas con voz."""
from unittest.mock import MagicMock, patch

from odoo.tests import TransactionCase, tagged

from .common import AgentMixin, draft_json, is_verifier, setup_agent

SPEECH = 'odoo.addons.chatroom_ai_agent_profile.models.chatroom.requests.post'


@tagged('post_install', '-at_install')
class TestCosts(AgentMixin, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.profile, cls.knowledge = setup_agent(cls.env)
        cls.agent = cls.env['res.users'].create({
            'name': 'Asesor Costos', 'login': 'asesor_costos_test',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])]})
        cls.partner = cls.env['res.partner'].create({'name': 'Mario Ruiz'})

    def test_prompt_starts_the_same_for_every_customer(self):
        """El comienzo idéntico se cobra con descuento (caché del proveedor)."""
        prompts = []
        for name in ('Mario Ruiz', 'Ana Paz'):
            partner = self.env['res.partner'].create({'name': name})
            channel = self._channel('¿Cuál es el horario de atención?', partner=partner)
            prompts.append(channel.with_context(chatroom_ai_guard_draft=True)._ai_build_conversation(
                extra_system=channel._ai_guarded_draft_prompt())[0]['content'])
        stable = self.profile._identity_prompt() + '\n\n' + self.profile._contract_prompt()
        self.assertTrue(all(prompt.startswith(stable) for prompt in prompts))
        self.assertGreater(len(stable), 3000)
        self.assertTrue(prompts[0].rstrip().endswith('Cliente: Ana Paz.'.replace('Ana Paz', 'Mario Ruiz')))
        self.assertLess(prompts[0].index('lunes a viernes'), prompts[0].index('DATOS DE ESTA CONVERSACIÓN'))

    def test_copied_answers_skip_the_verifier(self):
        reply = 'Horario de atención: lunes a viernes de 8:00 a 18:00.'
        with self._ai(draft_json(reply)) as seen, self._no_send():
            result = self._channel('¿Cuál es el horario de atención?').action_ai_auto_reply_safe()
        self.assertEqual(result['status'], 'sent')
        self.assertFalse(any(is_verifier(conversation) for conversation in seen))
        # En «Máxima calidad» se verifica siempre.
        self.profile.cost_mode = 'quality'
        with self._ai(draft_json(reply)) as seen, self._no_send():
            self._channel('¿Horario de atención?').action_ai_auto_reply_safe()
        self.assertTrue(any(is_verifier(conversation) for conversation in seen))

    def test_verifier_reads_only_the_information(self):
        reply = draft_json('No, atendemos de lunes a viernes; los sábados no abrimos.')
        with self._ai(reply) as seen, self._no_send():
            self._channel('¿Atienden los sábados?').action_ai_auto_reply_safe()
        verifier = next(conversation for conversation in seen if is_verifier(conversation))
        info = verifier[1]['content']
        self.assertIn('lunes a viernes', info)
        self.assertIn('muebles de oficina', info)
        self.assertNotIn('FORMATO DE RESPUESTA', info)
        self.assertNotIn('QUÉ DEBES HACER', info)
        self.assertLess(len(info), len(seen[0][0]['content']))

    def test_same_first_question_is_reused_without_ai(self):
        reply = 'Horario de atención: lunes a viernes de 8:00 a 18:00.'
        with self._ai(draft_json(reply)), self._no_send():
            self._channel('Hola, ¿cuál es el horario de atención?').action_ai_auto_reply_safe()
        self.assertEqual(self.env['chatroom.ai.reply.cache'].search_count([]), 1)
        other = self.env['res.partner'].create({'name': 'Otra Clienta'})
        with self._ai('no debería llamarse') as seen, self._no_send() as sender:
            result = self._channel('¿Horario de atención?', partner=other).action_ai_auto_reply_safe()
        self.assertFalse(seen, 'La misma pregunta se responde sin consultar a la IA.')
        self.assertEqual(result['status'], 'sent')
        self.assertEqual(sender.call_args.args[1], reply)
        event = self.env['chatroom.ai.agent.event'].search([], limit=1)
        self.assertTrue(event.cached)
        self.assertEqual(self.profile._dashboard_values()['reused'], 1)
        # Si cambia la información publicada, se vuelve a consultar.
        self.knowledge.write({'keyword_tags': 'horario, envíos, plan, precio, atención'})
        with self._ai(draft_json(reply)) as seen, self._no_send():
            self._channel('¿Horario de atención?', partner=self.env['res.partner'].create({'name': 'Z'})) \
                .action_ai_auto_reply_safe()
        self.assertTrue(seen)

    def test_personal_or_quality_answers_are_not_reused(self):
        with self._ai(draft_json('Hola Mario, atendemos de lunes a viernes de 8:00 a 18:00.')), self._no_send():
            self._channel('¿Cuál es el horario?').action_ai_auto_reply_safe()
        self.assertFalse(self.env['chatroom.ai.reply.cache'].search_count([]))
        self.profile.cost_mode = 'quality'
        with self._ai(draft_json('Horario de atención: lunes a viernes de 8:00 a 18:00.')), self._no_send():
            self._channel('¿Horario de atención?').action_ai_auto_reply_safe()
        self.assertFalse(self.env['chatroom.ai.reply.cache'].search_count([]))

    def test_back_and_forth_is_not_blocked_but_loops_are(self):
        """Antes: una respuesta cada 15 min dejaba sin respuesta al cliente de un guion."""
        channel = self._channel('Quiero cotizar escritorios')
        Message = self.env['chatroom.message']
        for text in ('¿Cuántos necesitas?', '¿A nombre de quién?'):
            Message.create({'channel_id': channel.id, 'direction': 'outbound', 'body': text, 'state': 'sent',
                            'ai_generated': True})
            self._inbound(channel, 'respuesta del cliente')
        with self._ai(draft_json('¿En qué ciudad estás?', intent='venta', backing='guion')), self._no_send():
            self.assertNotEqual(channel.action_ai_auto_reply_safe()['status'], 'cooldown')
        for _index in range(3):
            Message.create({'channel_id': channel.id, 'direction': 'outbound', 'body': 'x', 'state': 'sent',
                            'ai_generated': True})
        self._inbound(channel, '¿y el precio del plan?')
        with self._ai(draft_json('El plan básico cuesta 25 dólares mensuales.')), self._no_send():
            self.assertEqual(channel.action_ai_auto_reply_safe()['status'], 'cooldown',
                             '5 respuestas en 15 minutos: posible bucle.')

    # ------------------------------------------------------------------
    # Voz
    # ------------------------------------------------------------------
    def _audio_channel(self):
        channel = self._channel('')
        channel.message_ids.write({'message_type': 'audio', 'body': False,
                                   'ai_transcript': '¿Cuánto demoran los envíos?'})
        return channel

    def _send_patches(self):
        Channel = type(self.env['chatroom.channel'])
        return [patch.object(Channel, '_get_meta_credentials', return_value=('token', 'phone', 'v20.0')),
                patch.object(Channel, '_check_can_send', return_value=True),
                patch.object(Channel, '_deliver_media_message', return_value=True)]

    def test_voice_reply_when_customer_sent_audio(self):
        self.profile.voice_replies = 'audio'
        channel = self._audio_channel()
        speech = MagicMock(status_code=200, content=b'OggS-voz')
        patches = self._send_patches()
        for item in patches:
            item.start()
        try:
            with patch(SPEECH, return_value=speech) as post:
                channel.with_context(chatroom_ai_generated=True).action_send_text('Llegan en 48 horas.')
        finally:
            for item in patches:
                item.stop()
        self.assertTrue(post.call_args.args[0].endswith('/audio/speech'))
        self.assertEqual(post.call_args.kwargs['json']['voice'], 'nova')
        reply = channel.message_ids.filtered(lambda message: message.direction == 'outbound')
        self.assertEqual((reply.message_type, reply.ai_transcript), ('audio', 'Llegan en 48 horas.'))
        self.assertEqual(reply.attachment_ids.raw, b'OggS-voz')
        self.assertTrue(reply.ai_generated)

    def test_text_reply_when_voice_is_off_or_fails(self):
        channel = self._audio_channel()
        Channel = type(self.env['chatroom.channel'])
        with patch.object(Channel, '_ai_speech') as speech, \
                patch('odoo.addons.chatroom_whatsapp.models.chatroom_channel.ChatroomChannel.action_send_text',
                      autospec=True, return_value=True) as text_send:
            channel.with_context(chatroom_ai_generated=True).action_send_text('Llegan en 48 horas.')
            speech.assert_not_called()
            text_send.assert_called_once()
            self.profile.voice_replies = 'audio'
            speech.side_effect = RuntimeError('sin voz')
            channel.with_context(chatroom_ai_generated=True).action_send_text('Llegan en 48 horas.')
            self.assertEqual(text_send.call_count, 2, 'Si la voz falla, sale el texto.')

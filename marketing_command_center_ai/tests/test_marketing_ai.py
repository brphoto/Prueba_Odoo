from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

CANAL = ('odoo.addons.chatroom_ai_usage.models.chatroom_channel'
         '.ChatroomChannel._ai_chat_completion')


@tagged('post_install', '-at_install')
class TestMarketingAi(TransactionCase):
    """Consultas de marketing contra el proveedor de IA.

    El módulo no tenía tests y es el que decide qué datos de la empresa
    salen hacia un proveedor externo. Lo que se cubre es esa frontera:
    que el modo local no llame a nadie, que lo que se envía sean los
    datos del período y no otra cosa, y que un fallo quede registrado.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.chat = cls.env['marketing.social.agent.chat'].create({
            'name': 'Consulta QA',
        })

    # ------------------------------------------------------------------
    # El modo local no debe salir a la red
    # ------------------------------------------------------------------

    def test_local_mode_never_calls_the_provider(self):
        """El modo local existe precisamente para no gastar tokens."""
        self.chat.write({'analysis_mode': 'local', 'draft_message': '¿Cómo vamos?'})
        with patch(CANAL) as proveedor:
            self.chat.action_send_message()
        proveedor.assert_not_called()

    def test_provider_mode_requires_a_question(self):
        self.chat.write({'analysis_mode': 'provider', 'draft_message': '   '})
        with patch(CANAL) as proveedor:
            with self.assertRaises(UserError):
                self.chat.action_send_message()
        proveedor.assert_not_called()

    # ------------------------------------------------------------------
    # Qué se envía y qué se guarda
    # ------------------------------------------------------------------

    def test_a_successful_query_stores_the_answer_and_the_sources(self):
        self.chat.write({'analysis_mode': 'provider',
                         'draft_message': '¿Qué red rindió mejor?'})
        with patch(CANAL, return_value='Instagram lideró el alcance.'):
            self.chat.action_send_message()
        self.assertEqual(self.chat.state, 'answered')
        self.assertEqual(self.chat.answer, 'Instagram lideró el alcance.')
        self.assertTrue(self.chat.source_summary,
                        'Sin resumen de fuentes no se puede auditar la respuesta.')
        self.assertTrue(self.chat.ai_run_at)
        self.assertFalse(self.chat.ai_error)

    def test_the_question_and_the_answer_are_kept_in_the_conversation(self):
        """Las dos partes tienen que quedar, y en ese orden: el histórico
        es lo único que explica por qué se respondió eso."""
        self.chat.write({'analysis_mode': 'provider',
                         'draft_message': '¿Y el engagement?'})
        with patch(CANAL, return_value='Subió un 4%.'):
            self.chat.action_send_message()
        mensajes = self.chat.chat_message_ids.sorted('sequence')
        self.assertEqual(mensajes[-2].speaker, 'user')
        self.assertEqual(mensajes[-2].body, '¿Y el engagement?')
        self.assertEqual(mensajes[-1].speaker, 'agent')
        self.assertEqual(mensajes[-1].body, 'Subió un 4%.')

    def test_the_draft_is_cleared_after_answering(self):
        """Si el borrador se queda, el siguiente envío repite la pregunta."""
        self.chat.write({'analysis_mode': 'provider', 'draft_message': 'Hola'})
        with patch(CANAL, return_value='Respuesta.'):
            self.chat.action_send_message()
        self.assertFalse(self.chat.draft_message)

    def test_only_the_selected_period_is_sent(self):
        """Lo que sale de la empresa tiene que ser lo del período pedido.
        Se comprueba sobre el JSON real que recibe el proveedor."""
        self.chat.write({'analysis_mode': 'provider', 'period_days': 7,
                         'draft_message': 'Resumen'})
        recibido = {}

        def capturar(self_canal, mensajes, task_type=None, model_id=None):
            recibido['mensajes'] = mensajes
            return 'ok'

        with patch(CANAL, autospec=True, side_effect=capturar):
            self.chat.action_send_message()
        contenido = recibido['mensajes'][1]['content']
        self.assertIn('"periodo_dias": 7', contenido)
        self.assertIn('"pregunta": "Resumen"', contenido)

    def test_the_provider_is_told_not_to_invent_metrics(self):
        """La instrucción del sistema es la única barrera contra que el
        modelo se invente cifras. Si desaparece, nadie se entera."""
        self.chat.write({'analysis_mode': 'provider', 'draft_message': 'Resumen'})
        recibido = {}

        def capturar(self_canal, mensajes, task_type=None, model_id=None):
            recibido['sistema'] = mensajes[0]['content']
            return 'ok'

        with patch(CANAL, autospec=True, side_effect=capturar):
            self.chat.action_send_message()
        self.assertIn('No inventes métricas', recibido['sistema'])

    def test_the_summary_button_asks_the_provider(self):
        with patch(CANAL, return_value='Resumen ejecutivo.') as proveedor:
            self.chat.action_generate_ai_summary()
        proveedor.assert_called_once()
        self.assertEqual(self.chat.analysis_mode, 'provider')
        self.assertEqual(self.chat.answer, 'Resumen ejecutivo.')

    # ------------------------------------------------------------------
    # Cuando el proveedor falla
    # ------------------------------------------------------------------

    def test_a_failure_raises_and_delegates_the_diagnostic(self):
        """`action_send_message` guardaba el motivo y acto seguido lanzaba
        un `UserError`, que deshace la transacción: el motivo se perdía
        siempre. Aquí solo se comprueba el aviso y la delegación, porque
        `assertRaises` de Odoo envuelve el bloque en un savepoint y
        deshace cualquier escritura hecha dentro.
        """
        self.chat.write({'analysis_mode': 'provider', 'draft_message': 'Resumen'})
        ayudante = ('odoo.addons.marketing_command_center_ai.models'
                    '.marketing_social_agent.MarketingSocialAgentChat'
                    '._record_failed_query')
        with patch(CANAL, side_effect=ValueError('sin cuota')), \
                patch(ayudante) as registrar:
            with self.assertRaises(UserError):
                self.chat.action_send_message()
        registrar.assert_called_once()
        self.assertIn('sin cuota', str(registrar.call_args[0][0]))

    def test_the_reason_for_a_failure_is_actually_written(self):
        """El ayudante, probado sin `assertRaises` de por medio."""
        self.chat._record_failed_query(ValueError('sin cuota'))
        self.assertEqual(self.chat.state, 'error')
        self.assertIn('sin cuota', self.chat.ai_error or '')
        self.assertTrue(self.chat.ai_run_at)
        self.assertFalse(self.chat.answer)

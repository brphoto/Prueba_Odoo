from unittest.mock import patch

from psycopg2 import IntegrityError

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

AGENTE = 'odoo.addons.ai.models.ai_agent.AIAgent'


@tagged('post_install', '-at_install')
class TestChatroomAiOdooBridge(TransactionCase):
    """Puente entre Chatroom y la IA nativa de Odoo Enterprise.

    Este módulo es el único punto donde Chatroom habla con la aplicación
    IA de Odoo. Nunca tuvo tests. Lo que se cubre es lo que el usuario
    ve en el formulario (el estado de la integración) y lo que pasa
    cuando la IA nativa falla, que es el camino que estaba roto.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bridge = cls.env['chatroom.ai.odoo.bridge']._get_or_create_configuration()
        cls.agent = cls.env['ai.agent'].create({
            'name': 'Agente QA',
            'system_prompt': 'Responde corto.',
        })

    # ------------------------------------------------------------------
    # Estado de la integración
    # ------------------------------------------------------------------

    def test_without_an_agent_the_bridge_is_not_configured(self):
        self.bridge.native_agent_id = False
        self.assertEqual(self.bridge.state, 'not_configured')
        self.assertTrue(self.bridge.status_message)

    def test_with_an_active_agent_the_bridge_is_ready(self):
        self.bridge.native_agent_id = self.agent
        self.assertEqual(self.bridge.state, 'ready')

    def test_archiving_the_agent_takes_the_bridge_out_of_ready(self):
        """Si alguien archiva el agente desde la app de IA, el puente no
        puede seguir diciendo «Listo»: el siguiente intento fallaría."""
        self.bridge.native_agent_id = self.agent
        self.agent.active = False
        self.bridge.invalidate_recordset()
        self.assertEqual(self.bridge.state, 'not_configured')

    def test_deactivating_the_bridge_reports_it(self):
        self.bridge.native_agent_id = self.agent
        self.bridge.active = False
        self.assertEqual(self.bridge.state, 'not_configured')

    def test_only_one_configuration_per_company(self):
        """La acción del menú hace `_get_or_create_configuration`. Sin la
        restricción, dos usuarios entrando a la vez crearían dos.

        La restricción es de PostgreSQL, así que lo que sale es un
        `IntegrityError`, no un `ValidationError` del ORM.
        """
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            self.env['chatroom.ai.odoo.bridge'].create({
                'company_id': self.env.company.id,
            })
            self.env.flush_all()

    def test_the_configuration_is_reused_not_duplicated(self):
        modelo = self.env['chatroom.ai.odoo.bridge']
        self.assertEqual(modelo._get_or_create_configuration(), self.bridge)

    # ------------------------------------------------------------------
    # Lo que no se debe ejecutar
    # ------------------------------------------------------------------

    def test_the_test_needs_the_laboratory_enabled(self):
        self.bridge.write({'native_agent_id': self.agent.id,
                           'use_for_laboratory': False})
        with self.assertRaises(UserError):
            self.bridge.action_test_native()

    def test_the_test_needs_an_agent(self):
        self.bridge.write({'native_agent_id': False, 'use_for_laboratory': True})
        with self.assertRaises(UserError):
            self.bridge.action_test_native()

    def test_the_test_needs_a_question(self):
        self.bridge.write({'native_agent_id': self.agent.id,
                           'use_for_laboratory': True, 'test_question': '   '})
        with self.assertRaises(UserError):
            self.bridge.action_test_native()

    def test_syncing_sources_without_files_is_refused(self):
        self.bridge.write({'native_agent_id': self.agent.id,
                           'source_attachment_ids': [(5, 0, 0)]})
        with self.assertRaises(UserError):
            self.bridge.action_sync_sources()

    def test_opening_the_agent_without_one_is_refused(self):
        self.bridge.native_agent_id = False
        with self.assertRaises(UserError):
            self.bridge.action_open_native_agent()

    # ------------------------------------------------------------------
    # La prueba contra la IA nativa
    # ------------------------------------------------------------------

    def _prepare(self):
        self.bridge.write({
            'native_agent_id': self.agent.id,
            'use_for_laboratory': True,
            'test_question': '¿Qué vendemos?',
        })

    def test_a_successful_test_stores_the_answer_and_sends_nothing(self):
        """El laboratorio no puede mandarle nada al cliente: la respuesta
        se guarda en el formulario y ahí se queda."""
        self._prepare()
        with patch('%s.get_direct_response' % AGENTE,
                   return_value=['Vendemos Odoo.', 'Y consultoría.']):
            self.bridge.action_test_native()
        self.assertIn('Vendemos Odoo.', self.bridge.last_test_answer)
        self.assertIn('Y consultoría.', self.bridge.last_test_answer)
        self.assertEqual(self.bridge.last_test_question, '¿Qué vendemos?')
        self.assertFalse(self.bridge.last_error)
        self.assertTrue(self.bridge.last_tested_at)

    def test_an_empty_answer_is_reported_not_left_blank(self):
        self._prepare()
        with patch('%s.get_direct_response' % AGENTE, return_value=[]):
            self.bridge.action_test_native()
        self.assertTrue(self.bridge.last_test_answer,
                        'Una respuesta vacía debe explicarse, no dejar el campo en blanco.')

    def test_a_failed_test_raises_and_records_the_reason(self):
        """El fallo que estaba roto.

        `action_test_native` guardaba el motivo con un `write` normal y
        acto seguido lanzaba un `UserError`, que deshace la transacción
        entera: el motivo se perdía siempre y el formulario seguía
        mostrando la prueba anterior, sin rastro del error.

        Aquí solo se comprueba que el error llega al usuario y que se
        delega en el ayudante. Que el ayudante escriba de verdad se
        prueba aparte, porque `assertRaises` de Odoo envuelve el bloque
        en un savepoint y lo deshace al salir: cualquier escritura hecha
        dentro se pierde, venga de donde venga.
        """
        self._prepare()
        ayudante = ('odoo.addons.chatroom_ai_odoo_bridge.models'
                    '.chatroom_ai_odoo_bridge.ChatroomAiOdooBridge'
                    '._record_failed_test')
        with patch('%s.get_direct_response' % AGENTE,
                   side_effect=ValueError('sin cuota')), \
                patch(ayudante) as registrar:
            with self.assertRaises(UserError):
                self.bridge.action_test_native()
        registrar.assert_called_once()
        self.assertEqual(registrar.call_args[0][0], '¿Qué vendemos?')
        self.assertIn('sin cuota', str(registrar.call_args[0][1]))

    def test_the_reason_for_a_failure_is_actually_written(self):
        """El ayudante, probado sin `assertRaises` de por medio."""
        self._prepare()
        self.bridge._record_failed_test('¿Qué vendemos?', ValueError('sin cuota'))
        self.assertIn('sin cuota', self.bridge.last_error or '')
        self.assertEqual(self.bridge.last_test_question, '¿Qué vendemos?')
        self.assertTrue(self.bridge.last_tested_at)

    def test_a_broken_local_context_does_not_sink_the_test(self):
        """El contexto local es un complemento. Si no se puede reunir, la
        prueba sigue: antes un fallo de consulta ahí dejaba la
        transacción abortada y reventaba el write del final."""
        self._prepare()
        contexto = ('odoo.addons.chatroom_ai_odoo_bridge.models'
                    '.chatroom_ai_odoo_bridge.ChatroomAiOdooBridge._local_context')
        with patch(contexto, return_value=''), \
                patch('%s.get_direct_response' % AGENTE, return_value=['Listo']):
            self.bridge.action_test_native()
        self.assertEqual(self.bridge.last_test_answer, 'Listo')

    def test_the_local_context_is_sent_to_the_agent_and_saved(self):
        """Lo que se le manda al agente tiene que quedar a la vista: es la
        única forma de auditar qué datos salieron de Chatroom."""
        self._prepare()
        recibido = {}

        def capturar(self_agent, prompt, context_message='', enable_html_response=False):
            recibido['context'] = context_message
            return ['ok']

        contexto = ('odoo.addons.chatroom_ai_odoo_bridge.models'
                    '.chatroom_ai_odoo_bridge.ChatroomAiOdooBridge._local_context')
        with patch(contexto, return_value='CATALOGO: Odoo'), \
                patch('%s.get_direct_response' % AGENTE, autospec=True,
                      side_effect=capturar):
            self.bridge.action_test_native()
        self.assertIn('CATALOGO: Odoo', recibido['context'])
        self.assertEqual(self.bridge.local_knowledge_preview, 'CATALOGO: Odoo')

    # ------------------------------------------------------------------
    # Motor opcional
    # ------------------------------------------------------------------

    def test_marking_the_optional_backend_needs_an_agent(self):
        self.bridge.native_agent_id = False
        with self.assertRaises(UserError):
            self.bridge.action_prepare_optional_backend()

    def test_marking_the_optional_backend_does_not_switch_the_engine(self):
        """Marcarlo es una preferencia, no un cambio de motor: el núcleo
        actual de Chatroom tiene que seguir intacto."""
        self.bridge.native_agent_id = self.agent
        self.bridge.action_prepare_optional_backend()
        self.assertTrue(self.bridge.use_as_optional_backend)

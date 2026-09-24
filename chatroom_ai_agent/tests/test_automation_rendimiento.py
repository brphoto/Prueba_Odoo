# -*- coding: utf-8 -*-
from contextlib import contextmanager
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAutomatizacionCron(TransactionCase):
    """El cron de automatizaciones recorre conversaciones sin nadie delante.

    Dos cosas tienen que cumplirse ahí y no se notan en una prueba manual
    con tres canales:

    - Descartar los canales que ya tienen tarea no puede costar una
      consulta por canal.
    - Si una automatización falla, las demás conservan su trabajo. Antes
      se hacía `cr.rollback()`, que deshace la transacción entera.
    """

    def setUp(self):
        super().setUp()
        # Deterministas: nada de depender de una API configurada en la
        # base de desarrollo.
        parametros = self.env['ir.config_parameter'].sudo()
        parametros.set_param('chatroom_whatsapp.ai_enabled', 'False')
        parametros.set_param('chatroom_ai_agent.event_orchestration', 'False')
        parametros.set_param('chatroom_ai_agent.enabled', 'True')
        self.Automatizacion = self.env['chatroom.ai.automation']
        self.Tarea = self.env['chatroom.ai.task']

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    def _crear_canales(self, cuantos, prefijo='cron'):
        return self.env['chatroom.channel'].create([{
            'channel_type': 'whatsapp',
            'external_id': '%s-%s' % (prefijo, indice),
            'state': 'open',
        } for indice in range(cuantos)])

    def _crear_automatizacion(self, nombre, **valores):
        datos = {
            'name': nombre,
            'trigger': 'daily_review',
            'task_type': 'daily_review',
            'approval_required': True,
            'max_tasks': 50,
        }
        datos.update(valores)
        return self.Automatizacion.create(datos)

    def _ocupar(self, canales, tipo='daily_review', estado='awaiting_approval'):
        """Deja una tarea viva en cada canal, que es lo que hace que la
        automatización lo descarte."""
        return self.Tarea.sudo().create([{
            'name': 'Tarea viva %s' % canal.id,
            'channel_id': canal.id,
            'task_type': tipo,
            'state': estado,
        } for canal in canales])

    @contextmanager
    def _consultas(self):
        self.env.flush_all()
        medida = {'total': 0}
        inicio = self.env.cr.sql_log_count
        yield medida
        medida['total'] = self.env.cr.sql_log_count - inicio

    # ------------------------------------------------------------------
    # Que el descarte siga siendo correcto
    # ------------------------------------------------------------------

    def test_a_channel_that_already_has_a_live_task_is_skipped(self):
        canales = self._crear_canales(3, 'ocupados')
        self._ocupar(canales)
        automatizacion = self._crear_automatizacion('Descarte por lote')

        creadas = automatizacion._run_for_channels(canales)

        self.assertEqual(creadas, 0, 'No debía crearse ninguna tarea nueva.')
        ejecucion = automatizacion.run_ids[:1]
        self.assertEqual(ejecucion.tasks_reused, 3)
        self.assertEqual(
            self.Tarea.search_count([('channel_id', 'in', canales.ids)]), 3,
            'Se duplicaron tareas sobre canales que ya tenían una abierta.')

    def test_a_channel_with_only_a_finished_task_gets_a_new_one(self):
        """Solo bloquean las tareas vivas. Una terminada no puede dejar el
        canal fuera para siempre."""
        canal = self._crear_canales(1, 'terminada')
        self._ocupar(canal, estado='done')
        automatizacion = self._crear_automatizacion('Canal ya atendido ayer')

        creadas = automatizacion._run_for_channels(canal)

        self.assertEqual(creadas, 1)

    def test_a_live_task_of_another_type_does_not_block(self):
        """El descarte es por tipo de tarea: una cobranza abierta no debe
        impedir que se prepare una revisión diaria."""
        canal = self._crear_canales(1, 'otrotipo')
        self._ocupar(canal, tipo='collect_payment')
        automatizacion = self._crear_automatizacion('Revisión diaria')

        creadas = automatizacion._run_for_channels(canal)

        self.assertEqual(creadas, 1)

    def test_two_runs_in_a_row_do_not_duplicate(self):
        """La segunda pasada tiene que ver lo que creó la primera."""
        canales = self._crear_canales(2, 'dospasadas')
        automatizacion = self._crear_automatizacion('Dos pasadas seguidas')

        primera = automatizacion._run_for_channels(canales)
        segunda = automatizacion._run_for_channels(canales)

        self.assertEqual(primera, 2)
        self.assertEqual(segunda, 0, 'La segunda pasada duplicó las tareas.')

    # ------------------------------------------------------------------
    # Que descartar no cueste una consulta por canal
    # ------------------------------------------------------------------

    def test_skipping_does_not_cost_a_query_per_channel(self):
        """El caso normal del cron diario: casi todo ya está atendido.

        Con todos los canales ocupados no se crea nada, así que lo único
        que se mide es el descarte. Lo que esta prueba tiene que detectar
        es una consulta POR CANAL, no un número concreto.
        """
        pocos = self._crear_canales(3, 'pocos')
        self._ocupar(pocos)
        automatizacion = self._crear_automatizacion('Coste del descarte')
        with self._consultas() as coste_pocos:
            automatizacion._run_for_channels(pocos)

        muchos = self._crear_canales(40, 'muchos')
        self._ocupar(muchos)
        with self._consultas() as coste_muchos:
            automatizacion._run_for_channels(muchos)

        self.assertLessEqual(
            coste_muchos['total'], coste_pocos['total'] + 2,
            'Con 40 canales se hicieron %s consultas y con 3 se hicieron %s: '
            'el descarte está creciendo con el número de canales.'
            % (coste_muchos['total'], coste_pocos['total']))

    # ------------------------------------------------------------------
    # Que un fallo no se lleve por delante el trabajo de las demás
    # ------------------------------------------------------------------

    def _cron_con_una_que_falla(self, buena, mala, mensaje='fallo simulado'):
        original = type(self.Automatizacion)._run_for_channels

        def _falla_solo_la_mala(automatizacion, channels, execution_type='manual'):
            if automatizacion.id == mala.id:
                raise ValueError(mensaje)
            return original(automatizacion, channels,
                            execution_type=execution_type)

        with patch.object(type(self.Automatizacion), '_run_for_channels',
                          _falla_solo_la_mala):
            return self.Automatizacion._cron_run_scheduled()

    def test_a_failing_automation_does_not_undo_the_others(self):
        self._crear_canales(3, 'aislamiento')
        buena = self._crear_automatizacion('Va primero y funciona', sequence=1)
        mala = self._crear_automatizacion('Va después y revienta', sequence=2)

        total = self._cron_con_una_que_falla(buena, mala)

        supervivientes = self.Tarea.search_count([
            ('automation_id', '=', buena.id)])
        self.assertEqual(
            supervivientes, 3,
            'El fallo de la segunda automatización borró las tareas que '
            'había creado la primera.')
        self.assertEqual(
            total, supervivientes,
            'El cron informó de %s tareas creadas pero solo quedaron %s.'
            % (total, supervivientes))

    def test_the_run_of_the_healthy_automation_survives(self):
        self._crear_canales(2, 'historial')
        buena = self._crear_automatizacion('Deja historial', sequence=1)
        mala = self._crear_automatizacion('Revienta después', sequence=2)

        self._cron_con_una_que_falla(buena, mala)

        self.assertTrue(
            buena.run_ids,
            'La ejecución correcta desapareció del historial.')
        self.assertEqual(buena.run_ids[0].state, 'completed')

    def test_the_failure_leaves_a_trace_on_the_automation(self):
        self._crear_canales(1, 'rastro')
        buena = self._crear_automatizacion('Correcta', sequence=1)
        mala = self._crear_automatizacion('Fallida', sequence=2)

        self._cron_con_una_que_falla(buena, mala, mensaje='se cayó la API')

        self.assertIn('se cayó la API', mala.last_error or '')
        self.assertTrue(mala.last_run, 'No quedó constancia del intento.')

    def test_the_failure_leaves_a_run_in_the_history(self):
        """Sin esto la automatización fallida no aparece en ningún sitio:
        el usuario abre el historial y parece que el cron no la ejecutó."""
        self._crear_canales(1, 'historialfallo')
        buena = self._crear_automatizacion('Correcta', sequence=1)
        mala = self._crear_automatizacion('Fallida', sequence=2)

        self._cron_con_una_que_falla(buena, mala, mensaje='tiempo agotado')

        fallidas = mala.run_ids.filtered(lambda run: run.state == 'failed')
        self.assertTrue(
            fallidas, 'La ejecución fallida no quedó en el historial.')
        self.assertIn('tiempo agotado', fallidas[0].error_details or '')
        self.assertEqual(fallidas[0].execution_type, 'automatic')

    def test_the_cron_does_nothing_while_the_agent_is_disabled(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'chatroom_ai_agent.enabled', 'False')
        self._crear_canales(2, 'apagado')
        self._crear_automatizacion('No debería correr')

        self.assertEqual(self.Automatizacion._cron_run_scheduled(), 0)

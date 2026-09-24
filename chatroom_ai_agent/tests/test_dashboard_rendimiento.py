from contextlib import contextmanager

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestRendimientoPanelIA(TransactionCase):
    """El panel ejecutivo se recalcula en cada apertura y cada refresco.

    Los contadores se sacaban con un `search_count` por cada uno, todos
    sobre la misma tabla. Agrupando se recorre una sola vez.

    Lo que se fija aquí no es un número concreto de consultas —eso se
    rompería con cualquier cambio legítimo— sino que el coste NO crezca
    con el número de tareas. Esa es la diferencia entre una pantalla que
    va rápida hoy y una que va lenta dentro de un año.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.panel = cls.env['chatroom.ai.dashboard'].create({})
        cls.canal = cls.env['chatroom.channel'].create({
            'channel_type': 'whatsapp', 'external_id': '593999555000',
        })

    def _crear_tareas(self, cuantas, estado='draft'):
        return self.env['chatroom.ai.task'].create([{
            'name': 'Tarea QA %s %s' % (estado, indice),
            'channel_id': self.canal.id,
            'state': estado,
        } for indice in range(cuantas)])

    @contextmanager
    def _consultas(self):
        """Cuenta las consultas SQL que se hacen dentro del bloque."""
        self.env.flush_all()
        medida = {'total': 0}
        inicio = self.env.cr.sql_log_count
        yield medida
        medida['total'] = self.env.cr.sql_log_count - inicio

    # ------------------------------------------------------------------
    # Primero: que las cuentas sean correctas
    # ------------------------------------------------------------------

    def test_the_counters_add_up(self):
        self._crear_tareas(3, 'draft')
        self._crear_tareas(2, 'awaiting_approval')
        self._crear_tareas(1, 'failed')
        self.panel.invalidate_recordset()
        self.panel._compute_metrics()
        self.assertEqual(self.panel.total_tasks, 6)
        self.assertEqual(self.panel.approval_tasks, 2)
        self.assertEqual(self.panel.failed_tasks, 1)
        self.assertEqual(
            self.panel.pending_tasks, 2,
            'Pendientes son las que esperan aprobación, están planificadas '
            'o en marcha.')

    def test_a_state_with_no_tasks_counts_zero_not_missing(self):
        """Agrupar solo devuelve los estados que existen. Los que no
        aparecen tienen que salir como cero, no reventar."""
        self._crear_tareas(2, 'draft')
        self.panel.invalidate_recordset()
        self.panel._compute_metrics()
        self.assertEqual(self.panel.failed_tasks, 0)
        self.assertEqual(self.panel.approval_tasks, 0)
        self.assertEqual(self.panel.total_tasks, 2)

    def test_with_no_tasks_at_all_everything_is_zero(self):
        self.panel.invalidate_recordset()
        self.panel._compute_metrics()
        self.assertEqual(self.panel.total_tasks, 0)
        self.assertEqual(self.panel.pending_tasks, 0)

    # ------------------------------------------------------------------
    # Y después: que no crezca con los datos
    # ------------------------------------------------------------------

    def test_the_cost_does_not_grow_with_the_number_of_tasks(self):
        self._crear_tareas(5)
        self.panel.invalidate_recordset()
        with self._consultas() as pocas:
            self.panel._compute_metrics()

        self._crear_tareas(45)
        self.panel.invalidate_recordset()
        with self._consultas() as muchas:
            self.panel._compute_metrics()

        # Se compara con un margen de una consulta, no con igualdad
        # exacta: la primera pasada carga cosas en caché que la segunda
        # ya tiene, y eso mueve el número arriba o abajo sin que nada
        # dependa de los datos. Lo que este test tiene que detectar es
        # una consulta POR TAREA, que serían 45 más, no una de margen.
        self.assertLessEqual(
            muchas['total'], pocas['total'] + 1,
            'Con 50 tareas se hicieron %s consultas y con 5 se hicieron %s: '
            'el cómputo está creciendo con los datos.'
            % (muchas['total'], pocas['total']))

    def test_the_refresh_stays_within_a_sane_budget(self):
        """Un tope amplio, no una cifra exacta: lo que se quiere impedir
        es que alguien añada diez contadores sueltos sin darse cuenta."""
        self._crear_tareas(10)
        self.panel.invalidate_recordset()
        with self._consultas() as medida:
            self.panel._compute_metrics()
        self.assertLess(
            medida['total'], 40,
            'El refresco del panel hizo %s consultas. Si hacen falta '
            'tantas, conviene agrupar en vez de contar una por una.'
            % medida['total'])

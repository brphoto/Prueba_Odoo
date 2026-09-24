from datetime import date

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestKpiTargetMixin(TransactionCase):
    """Objetivos de KPI: el mixin compartido de `kpi_engine`.

    `kpi.target.mixin` es un modelo abstracto, así que no se puede probar
    por sí solo; solo existe a través de `chatroom.kpi.target` y de
    `crm.kpi.target`. Se prueba aquí, contra el modelo de Chatroom, que
    es uno de los dos que lo usan.

    Lo que decide este código es qué número se compara con el KPI, o sea
    si un indicador sale en verde o en rojo en el panel.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.kpi = cls.env['chatroom.kpi.definition'].create({
            'name': 'Conversaciones abiertas',
            'model_name': 'chatroom.channel',
            'aggregation': 'count',
            'target_value': 10.0,
            'goal_direction': 'higher',
        })

    def _target(self, **valores):
        return self.env['chatroom.kpi.target'].create(dict({
            'kpi_id': self.kpi.id,
            'target_value': 50.0,
            'goal_direction': 'higher',
        }, **valores))

    # ------------------------------------------------------------------
    # Qué objetivo se aplica
    # ------------------------------------------------------------------

    def test_without_targets_the_kpi_uses_its_own_value(self):
        self.assertEqual(self.kpi._get_effective_target(), (10.0, 'higher'))

    def test_a_global_target_replaces_the_kpi_value(self):
        self._target(scope_type='global', target_value=80.0)
        self.assertEqual(self.kpi._get_effective_target(), (80.0, 'higher'))

    def test_the_company_target_wins_over_the_global_one(self):
        """Lo concreto manda sobre lo general; si no, una empresa nunca
        podría apartarse del objetivo corporativo."""
        self._target(scope_type='global', target_value=80.0)
        self._target(scope_type='company', target_value=120.0,
                     company_id=self.env.company.id)
        self.assertEqual(self.kpi._get_effective_target(), (120.0, 'higher'))

    def test_a_target_of_another_company_is_ignored(self):
        otra = self.env['res.company'].create({'name': 'Otra empresa'})
        self._target(scope_type='company', target_value=999.0, company_id=otra.id)
        self.assertEqual(
            self.kpi._get_effective_target(), (10.0, 'higher'),
            'El objetivo de otra empresa no debe aplicarse a esta.')

    def test_an_archived_target_stops_applying(self):
        objetivo = self._target(scope_type='global', target_value=80.0)
        objetivo.active = False
        self.kpi.invalidate_recordset()
        self.assertEqual(self.kpi._get_effective_target(), (10.0, 'higher'))

    def test_the_direction_travels_with_the_target(self):
        """Un objetivo «menor o igual» invierte el semáforo. Si solo se
        tomara el número, un tiempo de respuesta bajo saldría en rojo."""
        self._target(scope_type='global', target_value=5.0, goal_direction='lower')
        self.assertEqual(self.kpi._get_effective_target(), (5.0, 'lower'))

    # ------------------------------------------------------------------
    # Vigencia
    # ------------------------------------------------------------------

    def test_a_custom_period_only_applies_inside_its_dates(self):
        objetivo = self._target(
            scope_type='global', period_type='custom',
            date_from=date(2026, 1, 1), date_to=date(2026, 3, 31))
        self.assertTrue(objetivo.is_current_period(date(2026, 2, 15)))
        self.assertTrue(objetivo.is_current_period(date(2026, 1, 1)),
                        'El primer día está dentro del período.')
        self.assertTrue(objetivo.is_current_period(date(2026, 3, 31)),
                        'El último día también.')
        self.assertFalse(objetivo.is_current_period(date(2025, 12, 31)))
        self.assertFalse(objetivo.is_current_period(date(2026, 4, 1)))

    def test_a_custom_period_with_one_open_end(self):
        desde = self._target(scope_type='global', period_type='custom',
                             date_from=date(2026, 1, 1))
        self.assertFalse(desde.is_current_period(date(2025, 6, 1)))
        self.assertTrue(desde.is_current_period(date(2030, 6, 1)))
        hasta = self._target(scope_type='global', period_type='custom',
                             date_to=date(2026, 1, 1))
        self.assertTrue(hasta.is_current_period(date(2020, 6, 1)))
        self.assertFalse(hasta.is_current_period(date(2030, 6, 1)))

    def test_an_expired_custom_target_falls_back_to_the_kpi_value(self):
        self._target(scope_type='global', period_type='custom',
                     target_value=80.0,
                     date_from=date(2020, 1, 1), date_to=date(2020, 12, 31))
        self.assertEqual(
            self.kpi._get_effective_target(), (10.0, 'higher'),
            'Un objetivo caducado no puede seguir marcando el semáforo.')

    def test_the_dates_must_be_in_order(self):
        with self.assertRaises(ValidationError):
            self._target(scope_type='global', period_type='custom',
                         date_from=date(2026, 3, 31), date_to=date(2026, 1, 1))

    def test_the_named_periods_apply_always(self):
        """Comportamiento actual, fijado a propósito.

        «Mensual», «Trimestral» y «Anual» no acotan nada: `is_current_period`
        solo mira las fechas del período «Personalizado», así que los tres
        se comportan igual que «Todo el tiempo». Quien elige «Mensual»
        esperando que el objetivo valga solo para el mes en curso no
        obtiene eso. No se cambia aquí porque cambiarlo movería el
        semáforo de indicadores que ya están en uso.
        """
        for periodo in ('all', 'monthly', 'quarterly', 'yearly'):
            objetivo = self._target(scope_type='global', period_type=periodo)
            self.assertTrue(
                objetivo.is_current_period(date(1999, 1, 1)),
                'Hoy «%s» no acota el período.' % periodo)
            objetivo.unlink()

    # ------------------------------------------------------------------
    # Alcances propios de Chatroom
    # ------------------------------------------------------------------

    def test_an_agent_target_needs_an_agent(self):
        with self.assertRaises(ValidationError):
            self._target(scope_type='agent', user_id=False)

    def test_a_line_target_needs_a_line(self):
        with self.assertRaises(ValidationError):
            self._target(scope_type='line', whatsapp_number_id=False)

    def test_agent_targets_do_not_reach_the_kpi_yet(self):
        """Comportamiento actual, fijado a propósito.

        `_get_effective_target` solo mira los alcances «company» y
        «global». Un objetivo por agente se puede crear y se valida, pero
        no cambia el semáforo: el KPI se calcula para toda la empresa y no
        hay un agente al que referirlo. Queda pendiente de decidir.
        """
        self._target(scope_type='agent', user_id=self.env.user.id,
                     target_value=999.0)
        self.assertEqual(self.kpi._get_effective_target(), (10.0, 'higher'))

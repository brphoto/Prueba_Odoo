from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPipelineIntelligence(TransactionCase):
    """Semáforo de salud del pipeline en la ficha del contacto.

    Este módulo no tenía tests y lo que calcula sale en la lista de
    contactos: cuántas oportunidades están en riesgo, cuánto capital
    hay atrapado y de qué color va el semáforo. Si el cálculo se
    equivoca, un comercial deja de llamar a quien debería.

    Lo que se cubre es el reparto por niveles de riesgo, la suma del
    capital, la herencia desde contactos hijo y la acción del botón.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.matriz = cls.env['res.partner'].create({'name': 'Grupo QA'})
        cls.filial = cls.env['res.partner'].create({
            'name': 'Filial QA', 'parent_id': cls.matriz.id,
        })
        cls.suelto = cls.env['res.partner'].create({'name': 'Cliente suelto QA'})
        cls.etapa = cls.env['crm.stage'].search([('is_won', '=', False)], limit=1)

    def _oportunidad(self, partner, nivel, capital=0.0, **valores):
        lead = self.env['crm.lead'].create(dict({
            'name': 'Oportunidad %s de %s' % (nivel, partner.name),
            'type': 'opportunity',
            'partner_id': partner.id,
            'stage_id': self.etapa.id,
        }, **valores))
        # Los dos campos los rellena el cron de estancamiento; aquí se
        # fijan a mano para poder comprobar el cálculo sin depender de él.
        lead.write({'stagnation_score': nivel,
                    'estimated_capital_trapped': capital})
        return lead

    # ------------------------------------------------------------------
    # El semáforo
    # ------------------------------------------------------------------

    def test_a_partner_without_opportunities_is_healthy(self):
        self.assertEqual(self.suelto.intelligence_pipeline_health, 'healthy')
        self.assertEqual(self.suelto.intelligence_stagnant_count, 0)
        self.assertEqual(self.suelto.intelligence_stagnant_capital, 0.0)

    def test_healthy_opportunities_do_not_raise_the_alarm(self):
        self._oportunidad(self.suelto, 'healthy', 5000.0)
        self.suelto.invalidate_recordset()
        self.assertEqual(self.suelto.intelligence_pipeline_health, 'healthy')
        self.assertEqual(self.suelto.intelligence_stagnant_count, 0,
                         'Una oportunidad sana no está en riesgo.')

    def test_a_warning_turns_the_light_amber(self):
        self._oportunidad(self.suelto, 'warning', 1000.0)
        self.suelto.invalidate_recordset()
        self.assertEqual(self.suelto.intelligence_pipeline_health, 'warning')
        self.assertEqual(self.suelto.intelligence_stagnant_count, 1)

    def test_the_worst_level_decides_the_colour(self):
        """Con una sana, una en precaución y una crítica, el semáforo no
        puede salir ámbar: lo que manda es la peor."""
        self._oportunidad(self.suelto, 'healthy', 100.0)
        self._oportunidad(self.suelto, 'warning', 200.0)
        self._oportunidad(self.suelto, 'critical', 300.0)
        self.suelto.invalidate_recordset()
        self.assertEqual(self.suelto.intelligence_pipeline_health, 'critical')

    def test_stagnant_and_dead_also_count_as_critical(self):
        for nivel in ('stagnant', 'dead'):
            partner = self.env['res.partner'].create({'name': 'QA %s' % nivel})
            self._oportunidad(partner, nivel, 50.0)
            partner.invalidate_recordset()
            self.assertEqual(partner.intelligence_pipeline_health, 'critical',
                             'El nivel «%s» debería ser crítico.' % nivel)

    # ------------------------------------------------------------------
    # El capital atrapado
    # ------------------------------------------------------------------

    def test_only_the_capital_at_risk_is_added_up(self):
        """La oportunidad sana no suma: si sumara, la cifra de capital
        atrapado sería la cartera entera y no querría decir nada."""
        self._oportunidad(self.suelto, 'healthy', 9000.0)
        self._oportunidad(self.suelto, 'warning', 1500.0)
        self._oportunidad(self.suelto, 'critical', 2500.0)
        self.suelto.invalidate_recordset()
        self.assertEqual(self.suelto.intelligence_stagnant_count, 2)
        self.assertAlmostEqual(self.suelto.intelligence_stagnant_capital,
                               4000.0, places=2)

    # ------------------------------------------------------------------
    # Contactos con hijos
    # ------------------------------------------------------------------

    def test_a_parent_sees_the_risk_of_its_children(self):
        """El responsable del grupo tiene que ver lo que pasa en las
        filiales; si no, el semáforo de la matriz siempre sale verde."""
        self._oportunidad(self.filial, 'critical', 7000.0)
        self.matriz.invalidate_recordset()
        self.assertEqual(self.matriz.intelligence_stagnant_count, 1)
        self.assertAlmostEqual(self.matriz.intelligence_stagnant_capital,
                               7000.0, places=2)
        self.assertEqual(self.matriz.intelligence_pipeline_health, 'critical')

    def test_a_child_does_not_see_the_risk_of_its_parent(self):
        """La herencia va hacia arriba, no hacia abajo."""
        self._oportunidad(self.matriz, 'critical', 7000.0)
        self.filial.invalidate_recordset()
        self.assertEqual(self.filial.intelligence_stagnant_count, 0)

    def test_the_risk_of_an_unrelated_partner_is_not_mixed_in(self):
        self._oportunidad(self.suelto, 'critical', 4000.0)
        self.matriz.invalidate_recordset()
        self.assertEqual(self.matriz.intelligence_stagnant_count, 0)

    def test_computing_a_batch_gives_the_same_as_one_by_one(self):
        """El cálculo agrupa por lotes para no hacer dos consultas por
        fila en la lista de contactos. El atajo no puede cambiar el
        resultado."""
        self._oportunidad(self.matriz, 'warning', 100.0)
        self._oportunidad(self.filial, 'critical', 200.0)
        self._oportunidad(self.suelto, 'dead', 300.0)
        todos = self.matriz | self.filial | self.suelto
        todos.invalidate_recordset()
        en_lote = {p.id: (p.intelligence_stagnant_count,
                          p.intelligence_pipeline_health) for p in todos}
        for partner in todos:
            partner.invalidate_recordset()
            self.assertEqual(
                (partner.intelligence_stagnant_count,
                 partner.intelligence_pipeline_health),
                en_lote[partner.id],
                'El cálculo por lotes difiere del individual en %s' % partner.name)

    # ------------------------------------------------------------------
    # Lo que se queda fuera
    # ------------------------------------------------------------------

    def test_won_opportunities_are_left_out(self):
        """Una oportunidad ganada ya no tiene capital atrapado."""
        ganada = self.env['crm.stage'].search([('is_won', '=', True)], limit=1)
        if not ganada:
            self.skipTest('La base no tiene una etapa ganada.')
        self._oportunidad(self.suelto, 'critical', 5000.0, stage_id=ganada.id)
        self.suelto.invalidate_recordset()
        self.assertEqual(self.suelto.intelligence_stagnant_count, 0)

    def test_archived_opportunities_are_left_out(self):
        lead = self._oportunidad(self.suelto, 'critical', 5000.0)
        lead.active = False
        self.suelto.invalidate_recordset()
        self.assertEqual(self.suelto.intelligence_stagnant_count, 0)

    def test_leads_that_are_not_opportunities_are_left_out(self):
        self._oportunidad(self.suelto, 'critical', 5000.0, type='lead')
        self.suelto.invalidate_recordset()
        self.assertEqual(self.suelto.intelligence_stagnant_count, 0)

    # ------------------------------------------------------------------
    # El botón
    # ------------------------------------------------------------------

    def test_the_button_opens_an_action_whose_views_all_resolve(self):
        """La acción arma la lista de vistas a mano. Si una referencia no
        existe, el botón revienta al pulsarlo y no antes."""
        accion = self.matriz.action_open_pipeline_intelligence()
        self.assertEqual(accion['res_model'], 'crm.lead')
        modos = [modo for _id, modo in accion['views']]
        self.assertEqual(modos, ['list', 'kanban', 'graph', 'pivot', 'form'])
        for vista_id, modo in accion['views']:
            if not vista_id:
                continue
            vista = self.env['ir.ui.view'].browse(vista_id)
            self.assertTrue(vista.exists(), 'Falta la vista %s.' % modo)
            self.assertEqual(vista.type, modo,
                             'La vista declarada como «%s» no lo es.' % modo)

    def test_the_button_only_shows_the_group_it_belongs_to(self):
        """Si el dominio no acota por contacto, el responsable del grupo
        acaba viendo el pipeline de toda la empresa."""
        accion = self.matriz.action_open_pipeline_intelligence()
        dominio = dict((c[0], c[2]) for c in accion['domain'])
        self.assertIn(self.matriz.id, dominio['partner_id'])
        self.assertIn(self.filial.id, dominio['partner_id'],
                      'Las filiales tienen que entrar.')
        self.assertNotIn(self.suelto.id, dominio['partner_id'],
                         'Un contacto ajeno no debe aparecer.')

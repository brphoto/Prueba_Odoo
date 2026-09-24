# -*- coding: utf-8 -*-
from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestComprobacionAprobacion(TransactionCase):
    """La comprobación de aprobación humana tiene que decir la verdad.

    Es un semáforo de seguridad: si dice verde, el usuario deja de mirar.
    Miraba `safety_profile`, que no lo consulta nadie a la hora de
    decidir, e ignoraba `mode`, que sí. Quien destildaba la casilla sin
    tocar el selector de perfil veía verde mientras la IA actuaba sola.
    """

    def setUp(self):
        super().setUp()
        self.icp = self.env['ir.config_parameter'].sudo()
        self.canal = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp',
            'external_id': 'aprobacion-qa-001',
            'state': 'open',
        })

    def _configurar(self, requiere, perfil, modo):
        self.icp.set_param('chatroom_ai_agent.require_approval', requiere)
        self.icp.set_param('chatroom_ai_agent.mode', modo)
        # Quien nunca ha tocado el selector de perfil no tiene ese
        # parámetro escrito. Es justo la situación que fallaba, asÃ­ que
        # hay que reproducirla borrándolo, no poniéndolo a un valor.
        self.env['ir.config_parameter'].sudo().search(
            [('key', '=', 'chatroom_ai_agent.safety_profile')]).unlink()
        if perfil:
            self.icp.set_param('chatroom_ai_agent.safety_profile', perfil)

    def _dice_protegido(self):
        estado, _detalle, _consejo = self.env['chatroom.operations.check']._evaluate(
            'human_approval')
        return estado == 'ok', estado

    def _pide_aprobacion_de_verdad(self):
        tarea = self.env['chatroom.ai.task'].create_from_channel(
            self.canal, task_type='daily_review', prompt='comprobación')
        return tarea.approval_required

    # ------------------------------------------------------------------

    def test_unticking_the_box_is_not_reported_as_protected(self):
        """El caso que fallaba: destildar la casilla sin tocar el perfil.

        El parámetro del perfil no llega a existir, `get_param` devolvía
        su 'supervised' por defecto y el `or` daba verde.
        """
        self._configurar('False', None, 'automatic')

        protegido, estado = self._dice_protegido()
        self.assertFalse(
            protegido,
            'La comprobación dice «%s» (protegido) con la aprobación '
            'desactivada y el modo automático.' % estado)
        self.assertFalse(self._pide_aprobacion_de_verdad())

    def test_the_default_install_is_protected(self):
        self._configurar('True', None, 'supervised')

        protegido, _estado = self._dice_protegido()
        self.assertTrue(protegido)
        self.assertTrue(self._pide_aprobacion_de_verdad())

    def test_the_automatic_preset_is_reported_as_an_error(self):
        self._configurar('False', 'automatic', 'automatic')

        _protegido, estado = self._dice_protegido()
        self.assertEqual(estado, 'error')
        self.assertFalse(self._pide_aprobacion_de_verdad())

    def test_the_mode_protecting_the_tasks_is_reported_as_partial(self):
        """Con el modo supervisado las tareas siguen pidiendo aprobación
        aunque la casilla esté desactivada, pero las respuestas
        automáticas ya no. Ni verde ni rojo: eso hay que decirlo."""
        self._configurar('False', None, 'supervised')

        _protegido, estado = self._dice_protegido()
        self.assertEqual(
            estado, 'warning',
            'Con el modo supervisado y la casilla desactivada la '
            'protección es parcial, y el semáforo tiene que reflejarlo.')
        self.assertTrue(
            self._pide_aprobacion_de_verdad(),
            'El modo supervisado fuerza la aprobación en las tareas.')

    def test_the_profile_selector_alone_does_not_turn_it_green(self):
        """Dejar el perfil en 'supervised' no protege nada por sí solo:
        lo que protege son los dos parámetros que su onchange escribe."""
        self._configurar('False', 'supervised', 'automatic')

        protegido, estado = self._dice_protegido()
        self.assertFalse(
            protegido,
            'El perfil guardado no impone nada; la comprobación dijo «%s».'
            % estado)
        self.assertFalse(self._pide_aprobacion_de_verdad())

    def test_the_setup_screen_agrees_with_the_check(self):
        """El mismo indicador está en la pantalla de puesta en marcha y
        tenía la misma lógica. Los dos sitios deben coincidir."""
        self._configurar('False', None, 'automatic')

        puesta_en_marcha = self.env['chatroom.ai.setup'].create({})
        puesta_en_marcha._refresh()

        self.assertFalse(
            puesta_en_marcha.security_ready,
            'La pantalla de puesta en marcha sigue dando por buena una '
            'configuración sin aprobación humana.')


@tagged('post_install', '-at_install')
class TestComprobacionWhatsapp(TransactionCase):

    def test_with_no_lines_the_message_does_not_talk_about_lines(self):
        """`any([])` es falso igual que «hay líneas pero sin credencial»,
        y el aviso mandaba a completar unas credenciales inexistentes."""
        self.env['chatroom.whatsapp.number'].sudo().search(
            [('active', '=', True)]).write({'active': False})

        estado, detalle, consejo = self.env['chatroom.operations.check']._evaluate(
            'whatsapp_connection')

        self.assertEqual(estado, 'warning')
        self.assertNotIn(
            'líneas activas, pero', detalle,
            'Sin ninguna línea dada de alta, el detalle seguía diciendo '
            'que las hay: %s' % detalle)
        self.assertIn('línea', consejo.lower())


@tagged('post_install', '-at_install')
class TestComprobacionesEnLote(TransactionCase):

    def test_the_missing_ones_are_created_without_duplicating_the_rest(self):
        """Se buscan los doce de una vez y se crean solo los que faltan.
        Si el lote se hiciera mal, aparecerían repetidos."""
        Check = self.env['chatroom.operations.check']
        Check.action_run_all()
        empresa = self.env.company.id
        Check.sudo().search(
            [('company_id', '=', empresa),
             ('code', 'in', ('ai_provider', 'odoo_catalog', 'cost_tracking'))]
        ).unlink()

        segundas = Check.action_run_all()

        self.assertEqual(len(segundas), 12)
        self.assertEqual(
            len(set(segundas.mapped('code'))), 12,
            'Algún código salió repetido al recrear los que faltaban.')
        self.assertEqual(
            Check.sudo().search_count([('company_id', '=', empresa)]), 12)


@tagged('post_install', '-at_install')
class TestPanelOperativo(TransactionCase):
    """El panel suma dinero. Los tests que habÃ­a solo comprobaban que
    fueran números; aquí se comprueba que sean los números correctos."""

    def _panel(self):
        panel = self.env['chatroom.operations.dashboard'].create({})
        panel._refresh_metrics()
        return panel

    def test_the_open_pipeline_adds_up_what_was_added(self):
        antes = self._panel()

        self.env['crm.lead'].create([{
            'name': 'QA pipeline %s' % indice,
            'type': 'opportunity',
            'expected_revenue': importe,
            'probability': 30,
            'company_id': self.env.company.id,
        } for indice, importe in enumerate((1500.0, 2500.0))])

        despues = self._panel()

        self.assertEqual(
            despues.open_opportunities - antes.open_opportunities, 2)
        self.assertAlmostEqual(
            despues.pipeline_value - antes.pipeline_value, 4000.0, places=2,
            msg='El pipeline se agrega en SQL; la suma tiene que cuadrar '
                'con lo que se acaba de crear.')

    def test_a_won_opportunity_does_not_count_as_open_pipeline(self):
        antes = self._panel()

        self.env['crm.lead'].create({
            'name': 'QA ganada', 'type': 'opportunity',
            'expected_revenue': 9999.0, 'probability': 100,
            'company_id': self.env.company.id,
        })

        despues = self._panel()

        self.assertEqual(
            despues.open_opportunities, antes.open_opportunities,
            'Una oportunidad al 100%% se colo en el pipeline abierto.')
        self.assertAlmostEqual(
            despues.pipeline_value, antes.pipeline_value, places=2)

    def test_the_trapped_capital_only_adds_the_stagnant_ones(self):
        if 'stagnation_score' not in self.env['crm.lead']._fields:
            self.skipTest('crm_stagnation_management no está instalado')
        antes = self._panel()

        self.env['crm.lead'].create({
            'name': 'QA sana', 'type': 'opportunity', 'probability': 40,
            'expected_revenue': 1000.0, 'company_id': self.env.company.id,
        }).write({'stagnation_score': 'healthy',
                  'estimated_capital_trapped': 700.0})
        self.env['crm.lead'].create({
            'name': 'QA estancada', 'type': 'opportunity', 'probability': 40,
            'expected_revenue': 1000.0, 'company_id': self.env.company.id,
        }).write({'stagnation_score': 'stagnant',
                  'estimated_capital_trapped': 300.0})

        despues = self._panel()

        self.assertAlmostEqual(
            despues.stagnant_capital - antes.stagnant_capital, 300.0, places=2,
            msg='El capital atrapado sumó también el de la oportunidad '
                'sana.')

    def test_the_ai_usage_counters_come_out_of_one_group(self):
        if 'chatroom.ai.usage.event' not in self.env:
            self.skipTest('chatroom_ai_usage no está instalado')
        antes = self._panel()

        Evento = self.env['chatroom.ai.usage.event'].sudo()
        ahora = fields.Datetime.now()
        Evento.create([
            {'request_date': ahora, 'total_tokens': 100, 'success': True},
            {'request_date': ahora, 'total_tokens': 250, 'success': True},
            {'request_date': ahora, 'total_tokens': 50, 'success': False},
        ])

        despues = self._panel()

        self.assertEqual(
            despues.ai_requests_today - antes.ai_requests_today, 3)
        self.assertEqual(
            despues.ai_tokens_today - antes.ai_tokens_today, 400,
            'Los tokens se suman en SQL, incluidos los de las fallidas.')
        self.assertEqual(
            despues.ai_failed_today - antes.ai_failed_today, 1)

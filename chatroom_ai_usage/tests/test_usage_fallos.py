# -*- coding: utf-8 -*-
from unittest.mock import patch

import requests

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestConsumoIaFallos(TransactionCase):
    """Qué pasa cuando OpenAI Platform no responde.

    Todo este camino no estaba probado, y tenía dos cosas rotas: salía
    con un AttributeError en vez del UserError previsto —porque el modelo
    llamaba a un ayudante de un mixin que no heredaba— y el indicador de
    Ajustes no llegaba nunca a registrar el fallo.
    """

    def setUp(self):
        super().setUp()
        self.Snapshot = self.env['chatroom.ai.usage.snapshot']
        self.icp = self.env['ir.config_parameter'].sudo()
        self.icp.set_param('chatroom_whatsapp.ai_admin_api_key', 'sk-admin-qa')
        self.icp.set_param('chatroom_whatsapp.ai_usage_last_status', 'ok')
        self.icp.set_param('chatroom_whatsapp.ai_usage_last_error', '')

    def _con_la_api_caida(self):
        def cae(*args, **kwargs):
            raise requests.RequestException('se cayó la red')
        return patch.object(type(self.Snapshot), '_fetch', staticmethod(cae))

    def _refrescar_esperando_fallo(self):
        """No se usa `assertRaises`: envuelve el bloque en un savepoint y
        lo deshace, así que borraría el rastro que aquí se comprueba."""
        try:
            self.Snapshot.action_refresh()
        except UserError as exc:
            return exc
        except Exception as exc:
            self.fail(
                'Se esperaba un UserError explicando el fallo y salió un '
                '%s: %s' % (type(exc).__name__, exc))
        self.fail('El refresco debería haber fallado.')

    # ------------------------------------------------------------------

    def test_a_dead_api_explains_itself_instead_of_crashing(self):
        """El modelo llamaba a `_persist_diagnostic_record` sin heredar el
        mixin que lo define: el usuario recibía un AttributeError en lugar
        del mensaje."""
        with self._con_la_api_caida():
            error = self._refrescar_esperando_fallo()

        self.assertIn('consumo', str(error).lower())

    def test_the_model_really_has_the_diagnostic_helpers(self):
        """Lo que fallaba no se veía leyendo la clase: el mixin estaba
        puesto en otro modelo del mismo fichero."""
        self.assertTrue(hasattr(self.Snapshot, '_persist_diagnostic_record'))
        self.assertTrue(hasattr(self.Snapshot, '_persist_diagnostic'))

    def test_a_dead_api_leaves_a_snapshot_with_the_reason(self):
        antes = self.Snapshot.search_count([])

        with self._con_la_api_caida():
            self._refrescar_esperando_fallo()

        self.assertEqual(
            self.Snapshot.search_count([]), antes + 1,
            'El resumen de diagnóstico no se creó.')
        ultimo = self.Snapshot.search([], order='id desc', limit=1)
        self.assertEqual(ultimo.state, 'error')
        self.assertIn('se cayó la red', ultimo.error_message or '')

    def test_the_settings_indicator_records_the_failure(self):
        """Antes solo llegaba a registrar los éxitos: el `raise` deshacía
        la transacción con la anotación dentro, así que Ajustes mostraba
        la última sincronización correcta y ningún error en rojo."""
        with self._con_la_api_caida():
            self._refrescar_esperando_fallo()

        self.assertEqual(
            self.icp.get_param('chatroom_whatsapp.ai_usage_last_status'),
            'error')
        self.assertIn(
            'se cayó la red',
            self.icp.get_param('chatroom_whatsapp.ai_usage_last_error') or '')

    def test_the_cron_survives_a_dead_api(self):
        """El cron solo atrapa UserError. Con el AttributeError se caía
        entero, y Odoo lo marcaba como trabajo fallido."""
        self.icp.set_param('chatroom_whatsapp.ai_usage_auto_refresh', 'True')

        with self._con_la_api_caida():
            try:
                resultado = self.Snapshot._cron_refresh_usage()
            except Exception as exc:
                self.fail('El cron reventó con %s: %s'
                          % (type(exc).__name__, exc))

        self.assertEqual(resultado, 0)

    def test_the_cron_survives_an_unexpected_error_too(self):
        """Atrapar solo `UserError` fue lo que convirtió un fallo de una
        consulta en la caída del trabajo programado. Lo imprevisto se
        registra en el log, pero no tumba el cron."""
        self.icp.set_param('chatroom_whatsapp.ai_usage_auto_refresh', 'True')

        def revienta(*args, **kwargs):
            raise AttributeError('algo que nadie previó')

        with patch.object(type(self.Snapshot), '_fetch', staticmethod(revienta)):
            try:
                resultado = self.Snapshot._cron_refresh_usage()
            except Exception as exc:
                self.fail('El cron reventó con %s: %s'
                          % (type(exc).__name__, exc))

        self.assertEqual(resultado, 0)
        self.assertEqual(
            self.icp.get_param('chatroom_whatsapp.ai_usage_last_status'),
            'error',
            'Un fallo interno tampoco puede dejar el indicador en verde.')

    def test_the_cron_does_nothing_while_the_refresh_is_off(self):
        self.icp.set_param('chatroom_whatsapp.ai_usage_auto_refresh', 'False')
        self.assertEqual(self.Snapshot._cron_refresh_usage(), 0)

    def test_the_connection_test_explains_a_missing_admin_key(self):
        self.env['ir.config_parameter'].sudo().search(
            [('key', '=', 'chatroom_whatsapp.ai_admin_api_key')]).unlink()

        try:
            self.Snapshot.action_test_platform_connection()
        except UserError as exc:
            self.assertIn('Admin API Key', str(exc))
        else:
            self.fail('Sin Admin API Key la prueba debería fallar.')

        self.assertEqual(
            self.icp.get_param('chatroom_whatsapp.ai_usage_last_status'),
            'missing_admin_key',
            'Tampoco quedaba constancia de que falte la clave.')

    def test_a_successful_refresh_clears_the_error(self):
        """El camino correcto no puede quedarse con el error anterior
        pegado en la pantalla."""
        respuestas = {
            'organization/usage/completions': {'data': [{'results': [
                {'num_model_requests': 3, 'input_tokens': 100,
                 'output_tokens': 50, 'model': 'gpt-4o-mini'}]}]},
            'organization/costs': {'data': [{'results': [
                {'amount': {'value': 0.12, 'currency': 'usd'},
                 'line_item': 'gpt-4o-mini'}]}]},
        }

        def responde(path, key, start_ts, end_ts, group_by=None):
            return respuestas[path]

        with patch.object(type(self.Snapshot), '_fetch', staticmethod(responde)):
            self.Snapshot.action_refresh()

        self.assertEqual(
            self.icp.get_param('chatroom_whatsapp.ai_usage_last_status'), 'ok')
        self.assertFalse(
            self.icp.get_param('chatroom_whatsapp.ai_usage_last_error'))
        ultimo = self.Snapshot.search([], order='id desc', limit=1)
        self.assertEqual(ultimo.state, 'ok')
        self.assertEqual(ultimo.request_count, 3)

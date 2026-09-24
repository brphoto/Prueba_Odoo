from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged

from ..models.social_network_api import (
    SocialNetworkAdapter, SocialNetworkApiError, SocialNetworkHttpClient)


@tagged('post_install', '-at_install')
class TestSocialNetworkConnectors(TransactionCase):
    def test_http_client_accumulates_pages(self):
        client = SocialNetworkHttpClient('qa-token', token_in_query=True)
        responses = {
            'https://social.test/feed': {
                'data': [{'id': '1'}],
                'paging': {'next': 'https://social.test/feed?after=next'},
            },
            'https://social.test/feed?after=next': {'data': [{'id': '2'}]},
        }
        client.request = lambda url, params=None, headers=None: responses[url]
        payload = client.paged('https://social.test/feed', max_pages=2)
        self.assertEqual([item['id'] for item in payload['data']], ['1', '2'])

    def test_http_client_accepts_youtube_items_pages(self):
        client = SocialNetworkHttpClient('qa-token')
        responses = {
            'https://social.test/feed': {
                'items': [{'id': '1'}],
                'nextPageToken': 'next',
                'paging': {'next': 'https://social.test/feed?page=2'},
            },
            'https://social.test/feed?page=2': {'items': [{'id': '2'}]},
        }
        client.request = lambda url, params=None, headers=None: responses[url]
        payload = client.paged('https://social.test/feed', max_pages=2)
        self.assertEqual([item['id'] for item in payload['data']], ['1', '2'])

    def test_epoch_conversion_is_stable(self):
        self.assertEqual(SocialNetworkAdapter.epoch_to_iso(0), '1970-01-01T00:00:00')
        self.assertFalse(SocialNetworkAdapter.epoch_to_iso('not-a-date'))

    def test_network_records_share_base_center_models(self):
        connection = self.env['marketing.social.network.connection'].create({
            'name': 'QA YouTube', 'platform': 'youtube', 'access_token': 'qa-token',
        })
        profile = self.env['marketing.social.network.profile'].create({
            'name': 'Canal QA', 'connection_id': connection.id,
            'external_id': 'channel-qa', 'follower_count': 25,
        })
        account = profile._ensure_social_account()
        self.assertEqual(account.platform, 'youtube')
        self.assertEqual(account.external_id, 'channel-qa')


@tagged('post_install', '-at_install')
class TestSincronizacionPerfil(TransactionCase):
    """Sincronización de un perfil social: lo que pasa cuando falla.

    Una sincronización toca cuatro sitios —el perfil, la cuenta, el
    registro de ejecución y las publicaciones— y todo ocurre en una sola
    transacción. Si algo revienta a mitad, lo importante es que quede
    constancia de por qué: sin eso, el usuario ve un error y una ficha
    que parece no haberse tocado nunca.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.connection = cls.env['marketing.social.network.connection'].create({
            'name': 'QA conexión', 'platform': 'instagram',
            'access_token': 'qa-token',
        })
        cls.profile = cls.env['marketing.social.network.profile'].create({
            'name': 'Perfil QA', 'connection_id': cls.connection.id,
            'external_id': 'perfil-qa', 'follower_count': 10,
        })
        cls.Log = cls.env['marketing.social.network.sync.log']

    class _Adaptador:
        """Adaptador de mentira: devuelve lo que se le diga, o falla."""

        def __init__(self, publicaciones=None, error=None, comentarios=None):
            self._publicaciones = publicaciones or []
            self._error = error
            self._comentarios = comentarios or {}

        def publications(self, profile):
            if self._error:
                raise self._error
            return self._publicaciones

        def comments(self, external_id):
            return self._comentarios.get(external_id, [])

    def _sincronizar(self, adaptador):
        with patch.object(type(self.connection), '_adapter',
                          return_value=adaptador):
            return self.profile._sync_one_profile()

    def _ultimo_log(self):
        return self.Log.search([('profile_id', '=', self.profile.id)],
                               order='id desc', limit=1)

    # ------------------------------------------------------------------
    # Camino correcto
    # ------------------------------------------------------------------

    def test_a_successful_sync_records_what_it_processed(self):
        adaptador = self._Adaptador(publicaciones=[{
            'external_id': 'pub-1', 'name': 'Publicación QA',
            'published_at': '2026-09-01T10:00:00',
            'metrics': {'reach': 100, 'likes': 5},
        }], comentarios={'pub-1': [{'external_id': 'com-1', 'body': 'Hola'}]})

        self.assertEqual(self._sincronizar(adaptador), 1)
        self.assertEqual(self.profile.state, 'connected')
        self.assertFalse(self.profile.last_error)
        self.assertEqual(self.profile.last_posts_count, 1)
        self.assertEqual(self.profile.last_comments_count, 1)
        log = self._ultimo_log()
        self.assertEqual(log.state, 'success')
        self.assertEqual(log.publications_count, 1)
        self.assertTrue(log.finished_at)

    def test_syncing_twice_does_not_duplicate_publications(self):
        """El mismo anuncio dos veces tiene que actualizarse, no
        duplicarse: si no, todas las métricas del panel salen dobladas."""
        adaptador = self._Adaptador(publicaciones=[{
            'external_id': 'pub-1', 'name': 'Publicación QA',
            'published_at': '2026-09-01T10:00:00',
            'metrics': {'reach': 100},
        }])
        self._sincronizar(adaptador)
        cuenta = self.profile.social_account_id
        primero = self.env['marketing.social.publication'].search_count(
            [('account_id', '=', cuenta.id)])

        self._sincronizar(adaptador)
        self.assertEqual(
            self.env['marketing.social.publication'].search_count(
                [('account_id', '=', cuenta.id)]),
            primero, 'Una segunda pasada no puede crear publicaciones nuevas.')

    # ------------------------------------------------------------------
    # Cuando falla
    # ------------------------------------------------------------------

    def test_an_api_failure_leaves_the_reason_on_the_profile(self):
        adaptador = self._Adaptador(
            error=SocialNetworkApiError('Instagram: token caducado'))
        with self.assertRaises(SocialNetworkApiError):
            self._sincronizar(adaptador)
        # `assertRaises` de Odoo envuelve el bloque en un savepoint y lo
        # deshace, así que aquí solo se comprueba que el error sale.
        # Que el motivo se guarde de verdad lo cubre el test de abajo.

    def test_the_execution_log_is_recreated_not_rewritten(self):
        """El fallo que estaba abierto.

        El registro de ejecución se crea al empezar la sincronización, o
        sea dentro de la misma transacción que el `raise` deshace.
        Reescribirlo desde otra transacción no sirve: esa fila todavía no
        existe fuera. Hay que volver a crearla.
        """
        adaptador = self._Adaptador(
            error=SocialNetworkApiError('Instagram: límite alcanzado'))
        antes = self.Log.search_count([('profile_id', '=', self.profile.id)])
        try:
            self._sincronizar(adaptador)
        except SocialNetworkApiError:
            pass
        logs = self.Log.search([('profile_id', '=', self.profile.id)])
        self.assertGreater(
            len(logs), antes,
            'Tiene que quedar un registro de la ejecución fallida.')
        fallido = logs.filtered(lambda registro: registro.state == 'error')
        self.assertTrue(fallido, 'Y tiene que estar marcado como error.')
        self.assertIn('límite alcanzado', fallido[-1].error_message or '')
        self.assertTrue(fallido[-1].finished_at,
                        'Sin hora de fin no se puede medir cuánto tardó en fallar.')

    def test_an_unexpected_failure_is_wrapped_for_the_user(self):
        """Un error de programación no debe llegar crudo a la pantalla."""
        adaptador = self._Adaptador(error=ValueError('algo interno'))
        with self.assertRaises(UserError):
            self._sincronizar(adaptador)

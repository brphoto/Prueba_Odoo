from datetime import datetime
from unittest.mock import patch

from odoo.tests.common import TransactionCase, tagged

from ..models.meta_api import MetaGraphClient, MetaGraphError


@tagged('post_install', '-at_install')
class TestMarketingMetaConnector(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.Connection = cls.env['marketing.meta.connection']
        cls.Page = cls.env['marketing.meta.page']

    def test_connection_discovers_multiple_pages(self):
        connection = self.Connection.create({
            'name': 'QA Meta conexión', 'app_id': 'qa-app',
            'user_access_token': 'qa-user-token', 'api_version': 'v25.0',
        })

        def fake_request(_client, path, params=None):
            if path == 'me/accounts':
                return {'data': [
                    {'id': 'qa-page-1', 'name': 'Página QA 1', 'access_token': 'page-token-1', 'fan_count': 10},
                    {'id': 'qa-page-2', 'name': 'Página QA 2', 'access_token': 'page-token-2', 'fan_count': 20},
                ]}
            raise AssertionError(path)

        with patch.object(MetaGraphClient, 'request', new=fake_request):
            connection.action_discover_pages()

        self.assertEqual(connection.page_count, 2)
        self.assertEqual(set(connection.page_ids.mapped('page_id')), {'qa-page-1', 'qa-page-2'})
        self.assertEqual(connection.state, 'connected')
        self.assertEqual(connection.page_ids.filtered(lambda page: page.page_id == 'qa-page-2').follower_count, 20)

    def test_page_sync_is_idempotent_and_updates_base_models(self):
        connection = self.Connection.create({
            'name': 'QA Meta sync', 'user_access_token': 'qa-token',
        })
        page = self.Page.create({
            'name': 'Página de sincronización', 'connection_id': connection.id,
            'page_id': 'qa-page-sync', 'page_access_token': 'qa-page-token',
        })
        post = {
            'id': 'qa-post-1', 'message': 'Publicación de prueba',
            'created_time': '2026-09-01T12:00:00+0000',
            'permalink_url': 'https://facebook.com/qa-post-1',
        }

        def fake_request(_client, path, params=None):
            if path == page.page_id:
                return {'id': page.page_id, 'name': page.name, 'fan_count': 42}
            if path == '%s/posts' % page.page_id:
                return {'data': [post]}
            if path == '%s/conversations' % page.page_id:
                return {'data': []}
            if path == 'qa-post-1/insights':
                return {'data': [
                    {'name': 'post_impressions', 'values': [{'value': 100}]},
                    {'name': 'post_impressions_unique', 'values': [{'value': 80}]},
                    {'name': 'post_reactions_by_type_total', 'values': [{'value': 7}]},
                ]}
            if path == 'qa-post-1/comments':
                return {'data': [{'id': 'qa-comment-1', 'message': 'Muy útil', 'created_time': '2026-09-01T13:00:00+0000'}]}
            raise AssertionError(path)

        with patch.object(MetaGraphClient, 'request', new=fake_request):
            page.action_sync_page()
            page.action_sync_page()

        account = page.social_account_id
        publication = self.env['marketing.social.publication'].search([
            ('external_id', '=', 'qa-post-1'), ('account_id', '=', account.id),
        ])
        interaction = self.env['marketing.social.interaction'].search([
            ('external_id', '=', 'qa-comment-1'),
        ])
        self.assertEqual(len(publication), 1)
        self.assertEqual(len(publication.metric_ids), 1)
        self.assertEqual(publication.latest_reach, 80)
        self.assertEqual(len(interaction), 1)
        self.assertEqual(page.state, 'connected')

    def test_client_never_sends_request_without_token(self):
        client = MetaGraphClient('')
        with self.assertRaisesRegex(Exception, 'Falta el token'):
            client.request('me')

    def test_paged_accumulates_all_pages(self):
        client = MetaGraphClient('qa-token')

        def fake_request(_client, path, params=None):
            if path == 'me/accounts':
                return {
                    'data': [{'id': 'page-1'}],
                    'paging': {'next': 'https://graph.facebook.com/v25.0/me/accounts?after=next'},
                }
            return {'data': [{'id': 'page-2'}]}

        with patch.object(MetaGraphClient, 'request', new=fake_request):
            result = client.paged('me/accounts', max_pages=2)
        self.assertEqual([row['id'] for row in result['data']], ['page-1', 'page-2'])

    def test_paged_safe_keeps_valid_rows_when_cursor_expires(self):
        client = MetaGraphClient('qa-token')

        def fake_request(_client, path, params=None):
            if path == 'page/conversations':
                return {
                    'data': [{'id': 'conversation-1'}],
                    'paging': {'next': 'https://graph.facebook.com/v25.0/page/conversations?after=expired'},
                }
            raise MetaGraphError('Meta: (#100) Invalid cursor provided')

        with patch.object(MetaGraphClient, 'request', new=fake_request):
            result = client.paged_safe('page/conversations')
        self.assertEqual([row['id'] for row in result['data']], ['conversation-1'])
        self.assertFalse(result['_paging_complete'])
        self.assertIn('Invalid cursor', result['_paging_error'])


@tagged('post_install', '-at_install')
class TestMetricasInstagram(TransactionCase):
    """Métricas de Instagram cuando Meta no las da.

    «No disponible» y «cero» no son lo mismo, y el producto entero se
    apoya en esa distinción: el panel las cuenta por separado y la
    instrucción que se le manda a la IA dice literalmente que una
    métrica no disponible no equivale a cero.

    La ruta de Facebook lo respetaba; la de Instagram no creaba ni el
    registro, así que la publicación aparecía como si nadie la hubiera
    medido nunca.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.connection = cls.env['marketing.meta.connection'].create({
            'name': 'QA métricas', 'app_id': 'qa-app',
            'user_access_token': 'qa-token', 'api_version': 'v25.0',
        })
        cls.page = cls.env['marketing.meta.page'].create({
            'connection_id': cls.connection.id,
            'page_id': 'qa-page-metricas',
            'name': 'Página QA métricas',
            'page_access_token': 'page-token',
        })
        cls.cuenta = cls.env['marketing.social.account'].create({
            'name': 'Cuenta QA Instagram', 'platform': 'instagram',
        })
        cls.publicacion = cls.env['marketing.social.publication'].create({
            'name': 'Publicación QA Instagram',
            'account_id': cls.cuenta.id,
            'external_id': 'ig-media-qa',
            'published_at': datetime(2026, 9, 1, 10, 0, 0),
        })
        cls.Snapshot = cls.env['marketing.social.metric.snapshot']

    def _snapshot(self):
        return self.Snapshot.search(
            [('publication_id', '=', self.publicacion.id)], order='id desc', limit=1)

    def _sincronizar(self, respuesta):
        """Ejecuta la sincronización con una respuesta de Graph simulada."""
        cliente = MetaGraphClient('qa-token')
        with patch.object(MetaGraphClient, 'request', new=respuesta):
            return self.page._sync_instagram_metrics(
                cliente, self.publicacion,
                {'id': 'ig-media-qa', 'media_type': 'IMAGE'})

    def test_metrics_that_arrive_are_marked_as_verified(self):
        def respuesta(_cliente, path, params=None):
            return {'data': [
                {'name': 'reach', 'values': [{'value': 120}]},
                {'name': 'total_interactions', 'values': [{'value': 15}]},
                {'name': 'saved', 'values': [{'value': 4}]},
            ]}

        self.assertFalse(self._sincronizar(respuesta))
        snapshot = self._snapshot()
        self.assertEqual(snapshot.metric_status, 'verified')
        self.assertEqual(snapshot.reach, 120)
        self.assertEqual(snapshot.saves, 4)
        self.assertFalse(snapshot.provider_error)

    def test_when_meta_gives_nothing_the_metric_is_unavailable_not_zero(self):
        """El fallo que estaba abierto.

        Sin registro, el contador «Métricas no disponibles» del panel no
        se enteraba nunca, y la publicación se leía como medida en cero.
        """
        def respuesta(_cliente, path, params=None):
            raise MetaGraphError('Meta: token caducado (código 190)')

        error = self._sincronizar(respuesta)
        self.assertTrue(error, 'El motivo tiene que volver a quien llama.')
        snapshot = self._snapshot()
        self.assertTrue(snapshot, 'Tiene que quedar un registro, aunque esté vacío.')
        self.assertEqual(snapshot.metric_status, 'unavailable')
        self.assertIn('190', snapshot.provider_error or '',
                      'El motivo de Meta tiene que quedar guardado.')

    def test_a_partial_answer_is_marked_as_partial(self):
        """Si llega una métrica y falla otra, no es ni verificada ni
        no disponible: es parcial, y hay que decirlo."""
        def respuesta(_cliente, path, params=None):
            metrica = (params or {}).get('metric', '')
            if ',' in metrica:
                raise MetaGraphError('Meta: lote rechazado')
            if metrica == 'reach':
                return {'data': [{'name': 'reach', 'values': [{'value': 55}]}]}
            raise MetaGraphError('Meta: métrica %s no disponible' % metrica)

        self.assertTrue(self._sincronizar(respuesta))
        snapshot = self._snapshot()
        self.assertEqual(snapshot.metric_status, 'partial')
        self.assertEqual(snapshot.reach, 55)

    def test_the_batch_failure_is_reported_not_swallowed(self):
        """El fallo de la llamada en lote se descartaba en silencio. Si
        además fallan las individuales, el usuario se quedaba sin saber
        por qué no hay métricas."""
        def respuesta(_cliente, path, params=None):
            raise MetaGraphError('Meta: límite de peticiones alcanzado')

        error = self._sincronizar(respuesta)
        self.assertIn('límite de peticiones', error)
        self.assertIn('insights', self._snapshot().provider_error or '',
                      'Debe constar que lo que falló fue la llamada en lote.')

    def test_syncing_twice_does_not_duplicate_the_daily_snapshot(self):
        """Una segunda pasada el mismo día actualiza, no acumula: si no,
        las medias del panel salen falseadas."""
        def respuesta(_cliente, path, params=None):
            return {'data': [{'name': 'reach', 'values': [{'value': 10}]}]}

        self._sincronizar(respuesta)
        primero = self.Snapshot.search_count(
            [('publication_id', '=', self.publicacion.id)])

        def respuesta2(_cliente, path, params=None):
            return {'data': [{'name': 'reach', 'values': [{'value': 30}]}]}

        self._sincronizar(respuesta2)
        self.assertEqual(
            self.Snapshot.search_count([('publication_id', '=', self.publicacion.id)]),
            primero, 'No debe crear un segundo registro del mismo día.')
        self.assertEqual(self._snapshot().reach, 30)

    def test_videos_also_ask_for_views(self):
        """Un reel sin reproducciones no se puede evaluar."""
        pedidas = []

        def respuesta(_cliente, path, params=None):
            pedidas.append((params or {}).get('metric', ''))
            return {'data': []}

        cliente = MetaGraphClient('qa-token')
        with patch.object(MetaGraphClient, 'request', new=respuesta):
            self.page._sync_instagram_metrics(
                cliente, self.publicacion,
                {'id': 'ig-media-qa', 'media_type': 'REELS'})
        self.assertTrue(any('views' in p for p in pedidas))

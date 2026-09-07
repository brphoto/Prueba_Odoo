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

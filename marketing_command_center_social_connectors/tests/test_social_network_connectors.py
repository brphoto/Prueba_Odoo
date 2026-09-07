from odoo.tests.common import TransactionCase, tagged

from ..models.social_network_api import SocialNetworkHttpClient, SocialNetworkAdapter


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

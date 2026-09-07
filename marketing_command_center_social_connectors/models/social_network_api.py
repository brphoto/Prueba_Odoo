import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class SocialNetworkApiError(Exception):
    """Error seguro y legible para el operador, sin exponer credenciales."""


class SocialNetworkHttpClient:
    def __init__(self, access_token='', api_key='', timeout=30, token_in_query=False):
        self.access_token = access_token or ''
        self.api_key = api_key or ''
        self.timeout = timeout
        self.token_in_query = token_in_query

    def request(self, url, params=None, headers=None, method='GET', body=None):
        query = dict(params or {})
        if self.api_key:
            query.setdefault('key', self.api_key)
        if self.access_token and self.token_in_query and method == 'GET':
            query.setdefault('access_token', self.access_token)
        if query:
            url = '%s%s%s' % (url, '&' if '?' in url else '?', urlencode(query))
        request_headers = {'Accept': 'application/json', 'User-Agent': 'Odoo marketing social connector/19.0'}
        request_headers.update(headers or {})
        request_body = None
        if body is not None:
            request_body = json.dumps(body).encode('utf-8')
            request_headers.setdefault('Content-Type', 'application/json')
        if self.access_token and not self.token_in_query:
            request_headers.setdefault('Authorization', 'Bearer %s' % self.access_token)
        request = Request(url, headers=request_headers, method=method, data=request_body)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode('utf-8')
                return json.loads(raw) if raw else {}
        except HTTPError as error:
            try:
                payload = json.loads(error.read().decode('utf-8'))
            except (ValueError, UnicodeDecodeError):
                payload = {}
            raise SocialNetworkApiError(self._error(payload, error.code)) from error
        except (URLError, TimeoutError, ValueError) as error:
            raise SocialNetworkApiError('No se pudo conectar con la red social: %s' % error) from error

    @staticmethod
    def _error(payload, status=None):
        error = payload.get('error') or payload.get('errors') or {}
        if isinstance(error, list):
            error = error[0] if error else {}
        message = error.get('message') if isinstance(error, dict) else str(error)
        message = message or payload.get('message') or ('HTTP %s' % status if status else 'Respuesta inválida')
        return 'API social: %s' % message

    def paged(self, url, params=None, headers=None, max_pages=5):
        payload = self.request(url, params, headers=headers)
        rows = list(payload.get('data') or payload.get('elements') or payload.get('items') or [])
        pages = 1
        next_url = (payload.get('paging') or {}).get('next')
        while next_url and pages < max_pages:
            payload = self.request(next_url, headers=headers)
            rows.extend(payload.get('data') or payload.get('elements') or payload.get('items') or [])
            next_url = (payload.get('paging') or {}).get('next')
            pages += 1
        if rows:
            payload['data'] = rows
        return payload


class SocialNetworkAdapter:
    platform = None

    def __init__(self, connection):
        self.connection = connection
        self.client = SocialNetworkHttpClient(
            access_token=connection.access_token,
            api_key=connection.api_key,
            token_in_query=self.platform == 'instagram',
        )

    def test(self):
        raise NotImplementedError

    def discover_profiles(self):
        return [self.profile(self.test())]

    def profile(self, values):
        return {
            'external_id': values.get('id') or values.get('open_id') or values.get('sub'),
            'name': values.get('name') or values.get('display_name') or values.get('localizedFirstName') or self.platform,
            'username': values.get('username') or values.get('vanityName') or False,
            'profile_url': values.get('link') or values.get('share_url') or False,
            'follower_count': values.get('followers_count') or values.get('follower_count') or 0,
        }

    def publications(self, profile):
        return []

    @staticmethod
    def epoch_to_iso(value):
        """Convierte timestamps Unix de proveedores a ISO sin depender de Odoo."""
        # OJO: `0 in (None, False, '')` es True en Python, porque
        # `0 == False`. Con la comparacion por pertenencia, la epoca Unix 0
        # (1970-01-01, un timestamp perfectamente valido que algunas APIs
        # devuelven) se descartaba como "sin valor".
        if value is None or value is False or value == '':
            return False
        try:
            return time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(float(value)))
        except (TypeError, ValueError, OverflowError):
            return False


class InstagramAdapter(SocialNetworkAdapter):
    platform = 'instagram'
    base_url = 'https://graph.facebook.com/v25.0'

    def test(self):
        return self.client.request('%s/me' % self.base_url, {'fields': 'id,name'})

    def discover_profiles(self):
        payload = self.client.paged('%s/me/accounts' % self.base_url, {
            'fields': 'id,name,instagram_business_account{id,name,username,followers_count}', 'limit': 100,
        })
        profiles = []
        for page in payload.get('data', []):
            instagram = page.get('instagram_business_account') or {}
            if instagram.get('id'):
                profile = self.profile(instagram)
                profile['page_name'] = page.get('name')
                profiles.append(profile)
        return profiles

    def publications(self, profile):
        payload = self.client.paged('%s/%s/media' % (self.base_url, profile.external_id), {
            'fields': 'id,caption,media_type,permalink,timestamp,like_count,comments_count',
            'limit': 100,
        })
        result = []
        for row in payload.get('data', []):
            result.append({
                'external_id': row.get('id'), 'name': (row.get('caption') or 'Publicación de Instagram')[:120],
                'caption': row.get('caption'), 'url': row.get('permalink'),
                'published_at': row.get('timestamp'), 'content_type': 'video' if row.get('media_type') == 'VIDEO' else 'post',
                'metrics': {'likes': row.get('like_count', 0), 'comments': row.get('comments_count', 0)},
            })
        return result

    def comments(self, publication_id):
        payload = self.client.paged('%s/%s/comments' % (self.base_url, publication_id), {
            'fields': 'id,text,username,timestamp', 'limit': 100,
        })
        return [{
            'external_id': row.get('id'), 'text': row.get('text'), 'author_name': row.get('username'),
            'interaction_date': row.get('timestamp'), 'interaction_type': 'comment',
        } for row in payload.get('data', [])]


class YouTubeAdapter(SocialNetworkAdapter):
    platform = 'youtube'
    base_url = 'https://www.googleapis.com/youtube/v3'

    def _headers(self):
        return {'Authorization': 'Bearer %s' % self.connection.access_token} if self.connection.access_token else {}

    def test(self):
        params = {'part': 'snippet,statistics,contentDetails'}
        if self.connection.external_account_id:
            params['id'] = self.connection.external_account_id
        else:
            params['mine'] = 'true'
        payload = self.client.request('%s/channels' % self.base_url, params, headers=self._headers())
        rows = payload.get('items') or []
        if not rows:
            raise SocialNetworkApiError('YouTube no devolvió ningún canal para este token.')
        return rows[0]

    def profile(self, values):
        snippet = values.get('snippet') or {}
        stats = values.get('statistics') or {}
        return {
            'external_id': values.get('id'), 'name': snippet.get('title') or 'Canal de YouTube',
            'username': snippet.get('customUrl'), 'profile_url': 'https://www.youtube.com/channel/%s' % values.get('id'),
            'follower_count': int(stats.get('subscriberCount') or 0),
            'uploads_playlist_id': (values.get('contentDetails') or {}).get('relatedPlaylists', {}).get('uploads'),
        }

    def discover_profiles(self):
        return [self.profile(self.test())]

    def publications(self, profile):
        playlist_id = profile.uploads_playlist_id
        if not playlist_id:
            return []
        items = self.client.paged('%s/playlistItems' % self.base_url, {
            'part': 'contentDetails,snippet', 'playlistId': playlist_id, 'maxResults': 50,
        }, headers=self._headers())
        video_ids = [item.get('contentDetails', {}).get('videoId') for item in items.get('items', [])]
        video_ids = [item for item in video_ids if item]
        if not video_ids:
            return []
        videos = self.client.request('%s/videos' % self.base_url, {
            'part': 'snippet,statistics', 'id': ','.join(video_ids),
        }, headers=self._headers()).get('items', [])
        result = []
        for row in videos:
            snippet, stats = row.get('snippet') or {}, row.get('statistics') or {}
            result.append({
                'external_id': row.get('id'), 'name': (snippet.get('title') or 'Video de YouTube')[:120],
                'caption': snippet.get('description'), 'url': 'https://www.youtube.com/watch?v=%s' % row.get('id'),
                'published_at': snippet.get('publishedAt'), 'content_type': 'video',
                'metrics': {'views': stats.get('viewCount', 0), 'likes': stats.get('likeCount', 0),
                            'comments': stats.get('commentCount', 0), 'shares': stats.get('shareCount', 0)},
            })
        return result


class LinkedInAdapter(SocialNetworkAdapter):
    platform = 'linkedin'
    base_url = 'https://api.linkedin.com'

    def _headers(self):
        return {
            'Authorization': 'Bearer %s' % self.connection.access_token,
            'LinkedIn-Version': self.connection.api_version or '202501',
            'X-Restli-Protocol-Version': '2.0.0',
        }

    def test(self):
        return self.client.request('%s/v2/userinfo' % self.base_url, headers=self._headers())

    def discover_profiles(self):
        if self.connection.external_account_id:
            return [{
                'external_id': self.connection.external_account_id,
                'name': 'Organización de LinkedIn',
                'profile_url': False,
                'follower_count': 0,
            }]
        return [self.profile(self.test())]

    def profile(self, values):
        return {
            'external_id': values.get('sub'), 'name': values.get('name') or 'Perfil de LinkedIn',
            'username': values.get('localizedFirstName'), 'profile_url': values.get('profile'),
            'follower_count': 0,
        }

    def publications(self, profile):
        author = self.connection.external_account_id or profile.external_id
        if not author:
            return []
        author_urn = author if str(author).startswith('urn:') else 'urn:li:organization:%s' % author
        payload = self.client.paged('%s/rest/posts' % self.base_url, {
            'q': 'author', 'author': author_urn, 'count': 100,
        }, headers=self._headers())
        result = []
        for row in payload.get('data') or payload.get('elements') or []:
            result.append({
                'external_id': row.get('id'), 'name': (row.get('commentary') or 'Publicación de LinkedIn')[:120],
                'caption': row.get('commentary'), 'url': row.get('permalink'),
                'published_at': row.get('publishedAt') or row.get('createdAt'), 'content_type': 'post',
                'metrics': {},
            })
        return result


class TikTokAdapter(SocialNetworkAdapter):
    platform = 'tiktok'
    base_url = 'https://open.tiktokapis.com/v2'

    def _headers(self):
        return {'Authorization': 'Bearer %s' % self.connection.access_token}

    def test(self):
        return self.client.request('%s/user/info/' % self.base_url, {
            'fields': 'open_id,display_name,avatar_url,follower_count',
        }, headers=self._headers())

    def profile(self, values):
        values = values.get('data', {}).get('user', values)
        return {
            'external_id': values.get('open_id'), 'name': values.get('display_name') or 'Cuenta de TikTok',
            'username': values.get('username'), 'profile_url': False,
            'follower_count': values.get('follower_count') or 0,
        }

    def publications(self, profile):
        payload = self.client.request('%s/video/list/' % self.base_url, {
            'fields': 'id,title,video_description,create_time,share_url,like_count,comment_count,share_count,view_count',
            'max_count': 20,
        }, headers=self._headers(), method='POST', body={})
        rows = payload.get('data', {}).get('videos', [])
        return [{
            'external_id': row.get('id'), 'name': (row.get('title') or row.get('video_description') or 'Video de TikTok')[:120],
            'caption': row.get('video_description') or row.get('title'), 'url': row.get('share_url'),
            'published_at': self.epoch_to_iso(row.get('create_time')),
            'content_type': 'video',
            'metrics': {'views': row.get('view_count', 0), 'likes': row.get('like_count', 0),
                        'comments': row.get('comment_count', 0), 'shares': row.get('share_count', 0)},
        } for row in rows]


ADAPTERS = {
    'instagram': InstagramAdapter,
    'youtube': YouTubeAdapter,
    'linkedin': LinkedInAdapter,
    'tiktok': TikTokAdapter,
}

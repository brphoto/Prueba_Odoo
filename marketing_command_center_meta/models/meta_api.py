import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class MetaGraphError(Exception):
    """Error legible para el usuario sin exponer tokens en el mensaje."""


class MetaGraphClient:
    def __init__(self, access_token, api_version='v25.0', timeout=30):
        self.access_token = access_token or ''
        self.api_version = (api_version or 'v25.0').strip().strip('/')
        self.timeout = timeout

    @property
    def base_url(self):
        return 'https://graph.facebook.com/%s' % self.api_version

    def _url(self, path, params=None):
        path = str(path or '').strip()
        if path.startswith('http://') or path.startswith('https://'):
            url = path
        else:
            url = '%s/%s' % (self.base_url, path.lstrip('/'))
        query = dict(params or {})
        query['access_token'] = self.access_token
        separator = '&' if '?' in url else '?'
        return '%s%s%s' % (url, separator, urlencode(query))

    def request(self, path, params=None):
        if not self.access_token:
            raise MetaGraphError('Falta el token de acceso de Meta.')
        request = Request(self._url(path, params), headers={
            'Accept': 'application/json',
            'User-Agent': 'Odoo marketing_command_center_meta/19.0',
        })
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode('utf-8'))
        except HTTPError as error:
            try:
                payload = json.loads(error.read().decode('utf-8'))
            except (ValueError, UnicodeDecodeError):
                payload = {}
            raise MetaGraphError(self._error_message(payload, error.code)) from error
        except (URLError, TimeoutError, ValueError) as error:
            raise MetaGraphError('No se pudo conectar con Meta: %s' % error) from error
        if payload.get('error'):
            raise MetaGraphError(self._error_message(payload, None))
        return payload

    def mutate(self, path, params=None):
        """Execute a controlled POST against Graph API."""
        if not self.access_token:
            raise MetaGraphError('Falta el token de acceso de Meta.')
        request = Request(
            self._url(path),
            data=urlencode(dict(params or {})).encode('utf-8'),
            headers={
                'Accept': 'application/json',
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'Odoo marketing_command_center_meta/19.0',
            },
            method='POST',
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode('utf-8'))
        except HTTPError as error:
            try:
                payload = json.loads(error.read().decode('utf-8'))
            except (ValueError, UnicodeDecodeError):
                payload = {}
            raise MetaGraphError(self._error_message(payload, error.code)) from error
        except (URLError, TimeoutError, ValueError) as error:
            raise MetaGraphError('No se pudo conectar con Meta: %s' % error) from error
        if payload.get('error'):
            raise MetaGraphError(self._error_message(payload, None))
        return payload

    def _error_message(self, payload, status):
        error = payload.get('error') or {}
        message = error.get('message') or ('HTTP %s de Meta' % status if status else 'Respuesta inválida de Meta')
        code = error.get('code')
        return 'Meta: %s%s' % (message, ' (código %s)' % code if code else '')

    def paged(self, path, params=None, max_pages=5):
        payload = self.request(path, params)
        rows = list(payload.get('data') or [])
        pages = 1
        while payload.get('paging', {}).get('next') and pages < max_pages:
            payload = self.request(payload['paging']['next'])
            rows.extend(payload.get('data') or [])
            pages += 1
        if rows:
            payload['data'] = rows
        return payload

    def paged_safe(self, path, params=None, max_pages=20):
        """Read as many valid Graph pages as possible without losing prior rows.

        Meta can occasionally return an expired/invalid cursor for an older
        page.  The regular ``paged`` helper raises at that point and callers
        lose the batch already received.  Inbox synchronization is more useful
        when it keeps the valid rows and reports the cursor problem separately.
        """
        payload = self.request(path, params)
        first_payload = payload
        rows = list(payload.get('data') or [])
        pages = 1
        paging_error = False
        while payload.get('paging', {}).get('next') and pages < max_pages:
            try:
                payload = self.request(payload['paging']['next'])
            except MetaGraphError as error:
                paging_error = str(error)
                break
            rows.extend(payload.get('data') or [])
            pages += 1
        result = dict(first_payload)
        result['data'] = rows
        result['_pages_read'] = pages
        result['_paging_complete'] = not bool(payload.get('paging', {}).get('next'))
        result['_paging_error'] = paging_error
        if pages >= max_pages and payload.get('paging', {}).get('next'):
            result['_paging_complete'] = False
            result['_paging_error'] = 'Se alcanzó el límite de %s páginas de Meta.' % max_pages
        return result

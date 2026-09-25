# -*- coding: utf-8 -*-
"""Información en un paso: guardar = publicar, y cargar la web de la empresa."""
import ipaddress
import logging
import re
import socket
from urllib.parse import urldefrag, urljoin, urlparse

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

MAX_BYTES = 1500000
MAX_TEXT = 60000
SKIP_EXT = re.compile(r'\.(jpg|jpeg|png|gif|webp|svg|pdf|zip|rar|mp4|mp3|css|js|xml|ico)(\?|$)', re.I)


def check_public_url(url):
    """Solo http(s) hacia direcciones públicas: nunca la red interna del servidor."""
    parsed = urlparse(url or '')
    if parsed.scheme not in ('http', 'https') or not parsed.hostname:
        raise UserError(_('Usa una dirección web que empiece con http:// o https://'))
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80))
    except socket.gaierror:
        raise UserError(_('No se encontró el sitio %s.') % parsed.hostname)
    for info in infos:
        address = ipaddress.ip_address(info[4][0].split('%')[0])
        if (address.is_private or address.is_loopback or address.is_link_local or address.is_reserved
                or address.is_multicast or address.is_unspecified):
            raise UserError(_('Solo se pueden cargar sitios públicos de internet.'))
    return url


def fetch_page(url, timeout=15):
    """(url final, html) siguiendo hasta 3 redirecciones, cada una verificada."""
    for _hop in range(4):
        check_public_url(url)
        response = requests.get(url, timeout=timeout, allow_redirects=False, stream=True,
                                headers={'User-Agent': 'OdooChatroomAI/1.0 (+importar conocimiento)'})
        if response.is_redirect or response.status_code in (301, 302, 303, 307, 308):
            url = urljoin(url, response.headers.get('Location') or '')
            response.close()
            continue
        response.raise_for_status()
        kind = response.headers.get('Content-Type', '')
        if 'html' not in kind and 'text' not in kind:
            response.close()
            return url, ''
        raw = b''
        for block in response.iter_content(65536):
            raw += block
            if len(raw) > MAX_BYTES:
                break
        response.close()
        return url, decode_html(raw, kind)
    raise UserError(_('El sitio redirige demasiadas veces.'))


def decode_html(raw, content_type=''):
    """Texto de la página. Sin «charset» en la cabecera, requests supone
    Latin-1 y las tildes salen como «Ã¡»: se usa el de la página o UTF-8."""
    match = re.search(r'charset=["\']?([\w-]+)', content_type or '', re.I) or \
        re.search(rb'<meta[^>]+charset=["\']?([\w-]+)', raw[:4096], re.I)
    charset = match.group(1) if match else 'utf-8'
    charset = charset.decode('ascii', 'ignore') if isinstance(charset, bytes) else charset
    try:
        return raw.decode(charset, errors='replace')
    except LookupError:
        return raw.decode('utf-8', errors='replace')


def page_key(url):
    """La misma página con http/https, «www» o barra final."""
    parsed = urlparse(url)
    host = (parsed.hostname or '').removeprefix('www.')
    return '%s%s?%s' % (host, parsed.path.rstrip('/') or '/', parsed.query)


def page_text(html, base_url):
    """(título, texto legible, enlaces del mismo sitio)."""
    from lxml import html as lxml_html
    if not (html or '').strip():
        return '', '', []
    try:
        tree = lxml_html.fromstring(html)
    except Exception:  # noqa: BLE001 - HTML ilegible
        return '', '', []
    title = ' '.join((tree.findtext('.//title') or '').split())[:120]
    links = []
    host = urlparse(base_url).hostname
    for href in tree.xpath('//a/@href'):
        link = urldefrag(urljoin(base_url, href))[0]
        if urlparse(link).hostname == host and link.startswith('http') and not SKIP_EXT.search(link):
            links.append(link)
    for bad in tree.xpath('//script|//style|//noscript|//svg|//nav|//footer|//header|//form|//iframe'):
        bad.drop_tree()
    lines = []
    for block in tree.xpath('//h1|//h2|//h3|//h4|//p|//li|//td|//th|//dt|//dd|//blockquote'):
        text = ' '.join(block.text_content().split())
        if len(text) >= 3 and text not in lines[-3:]:
            lines.append(('\n## %s' % text) if block.tag in ('h1', 'h2', 'h3') else text)
    text = '\n'.join(lines).strip()
    if len(text) < 80:
        body = tree.find('.//body')
        text = ' '.join((body.text_content() if body is not None else tree.text_content()).split())
    return title, text[:MAX_TEXT], list(dict.fromkeys(links))


class AiKnowledgeBase(models.Model):
    _inherit = 'ai.knowledge.base'

    source_url = fields.Char(string='Página web de origen', readonly=True)

    def action_index_and_publish(self):
        """Un paso: la IA lo usa desde el siguiente mensaje."""
        self.action_index()
        failed = self.filtered(lambda manual: manual.state != 'indexed')
        if failed:
            raise UserError(_('No se pudo preparar «%(name)s»: %(error)s') % {
                'name': failed[0].name, 'error': failed[0].processing_error or _('sin contenido')})
        self.action_publish()
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'type': 'success', 'sticky': False, 'title': _('Publicado'),
            'message': _('La IA ya usa esta información en sus respuestas.'),
            'next': {'type': 'ir.actions.act_window_close'}}}


class ChatroomAiWebImport(models.TransientModel):
    _name = 'chatroom.ai.web.import'
    _description = 'Cargar información desde la web de la empresa'

    url = fields.Char(string='Página web', required=True, help='Ej.: https://www.miempresa.com/preguntas-frecuentes')
    max_pages = fields.Integer(string='Páginas a leer', default=5,
                               help='La página indicada y las enlazadas del mismo sitio, hasta este número.')
    publish = fields.Boolean(string='Publicar al terminar', default=True)
    result = fields.Text(string='Resultado', readonly=True)
    state = fields.Selection([('draft', 'Nuevo'), ('done', 'Listo')], default='draft')

    @api.constrains('max_pages')
    def _check_max_pages(self):
        for wizard in self:
            if not 1 <= wizard.max_pages <= 20:
                raise UserError(_('Lee entre 1 y 20 páginas.'))

    def _fetch(self, url):
        """Separado para poder probarlo sin internet."""
        return fetch_page(url)

    def action_import(self):
        self.ensure_one()
        url = (self.url or '').strip()
        if '://' not in url:
            url = 'https://%s' % url
        check_public_url(url)
        Knowledge = self.env['ai.knowledge.base'].sudo()
        queue, seen, created, errors, texts = [url], set(), Knowledge.browse(), [], set()
        while queue and len(seen) < self.max_pages:
            page = queue.pop(0)
            if page_key(page) in seen:
                continue
            seen.add(page_key(page))
            try:
                final_url, html = self._fetch(page)
                title, text, links = page_text(html, final_url)
            except UserError as exc:
                if page == url:
                    raise
                errors.append('%s: %s' % (page, exc.args[0]))
                continue
            except Exception as exc:  # noqa: BLE001 - una página caída no frena las demás
                if page == url:
                    raise UserError(_('No se pudo leer %(url)s: %(error)s') % {'url': page, 'error': exc})
                errors.append('%s: %s' % (page, exc))
                continue
            queue.extend(link for link in links if page_key(link) not in seen)
            if len(text) < 40 or text in texts:
                continue  # sin contenido, o la misma página con otra dirección
            texts.add(text)
            existing = Knowledge.search([('source_url', '=', final_url)], limit=1)
            values = {'name': title or final_url, 'source_type': 'text', 'source_text': text,
                      'source_url': final_url, 'publication_state': 'draft'}
            if existing:
                existing.write(values)
                created |= existing
            else:
                created |= Knowledge.create(values)
        if not created:
            raise UserError(_('No se encontró texto útil en %s.') % url)
        created.action_index()
        if self.publish:
            created.filtered(lambda manual: manual.state == 'indexed').action_publish()
        lines = [_('%s página(s) cargada(s):') % len(created)] + ['• %s' % manual.name for manual in created]
        if errors:
            lines += ['', _('No se pudieron leer:')] + ['• %s' % error for error in errors[:5]]
        self.write({'result': '\n'.join(lines), 'state': 'done'})
        return {'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': self.id,
                'view_mode': 'form', 'target': 'new', 'name': _('Cargar desde la web')}

# -*- coding: utf-8 -*-
"""Búsqueda en el conocimiento que entiende lo que el cliente quiso decir.

La búsqueda base es por palabras exactas: «costo» no encuentra «precio» ni
«envios» encuentra «envío». Aquí se suman tres capas:

1. Palabras sin tildes y sin plural.
2. Sinónimos del negocio (configurables en el perfil del agente).
3. Búsqueda por significado con embeddings del mismo proveedor de IA, que se
   calculan al indexar. Si el proveedor no los ofrece, sigue la búsqueda por
   palabras sin interrumpir nada.
"""
import hashlib
import json
import logging
import math
import re
from datetime import timedelta

import requests

from odoo import _, api, fields, models

from odoo.addons.chatroom_ai_learning.models.learning_utils import normalize

_logger = logging.getLogger(__name__)

STOPWORDS = {
    'para', 'como', 'esta', 'este', 'cliente', 'quiero', 'necesito', 'tiene', 'desde', 'una', 'uno', 'sobre',
    'debe', 'hola', 'buenas', 'buenos', 'dias', 'tardes', 'noches', 'porfa', 'favor', 'gracias', 'ustedes',
    'tienen', 'hacen', 'pueden', 'puedo', 'quisiera', 'saber', 'donde', 'cuando', 'cual', 'cuales', 'tengo',
    'estoy', 'estan', 'algo', 'mucho', 'muchas', 'the', 'and', 'you', 'your', 'with',
}
QUERY_CACHE = 'chatroom_ai_agent_profile.query_embeddings'
EMBED_BATCH = 64
SEMANTIC_MIN = 0.30     # similitud mínima para considerar un fragmento relacionado
SEMANTIC_WEIGHT = 6.0   # cuánto pesa el significado frente a las palabras


def stem(word):
    """Raíz simple en español: «envíos» → «envio», «precios» → «precio»."""
    # Primero la «s» y luego la «e» final, igual para singular y plural:
    # «elevables»/«elevable» → «elevabl», «ciudades»/«ciudad» → «ciudad».
    word = normalize(word)
    for suffix in ('s', 'e'):
        if len(word) > 4 and word.endswith(suffix):
            word = word[:-1]
    return word


def terms_of(text, minimum=4):
    return {stem(word) for word in re.findall(r'[a-z0-9]+', normalize(text or ''))
            if len(word) >= minimum and word not in STOPWORDS}


def parse_synonyms(raw):
    """«precio: costo, valor» → grupos de raíces equivalentes."""
    groups = []
    for line in (raw or '').splitlines():
        words = [part for part in re.split(r'[:,;=]', line) if part.strip()]
        group = set()
        for word in words:
            group |= terms_of(word, minimum=3)
        if len(group) > 1:
            groups.append(group)
    return groups


def cosine(first, second):
    dot = sum(a * b for a, b in zip(first, second))
    norm = math.sqrt(sum(a * a for a in first)) * math.sqrt(sum(b * b for b in second))
    return dot / norm if norm else 0.0


class AiKnowledgeChunk(models.Model):
    """Fragmento indexado de un conocimiento, con su vector de significado."""
    _name = 'ai.knowledge.chunk'
    _description = 'Fragmento de conocimiento para búsqueda por significado'
    _order = 'knowledge_id, sequence'

    knowledge_id = fields.Many2one('ai.knowledge.base', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer()
    digest = fields.Char(index=True)
    embedding = fields.Text()
    embedding_model = fields.Char()


class AiKnowledgeBase(models.Model):
    _inherit = 'ai.knowledge.base'

    chunk_ids = fields.One2many('ai.knowledge.chunk', 'knowledge_id', string='Fragmentos con significado')
    semantic_ready = fields.Boolean(string='Búsqueda por significado lista', compute='_compute_semantic_ready')

    def _compute_semantic_ready(self):
        for manual in self:
            manual.semantic_ready = bool(manual.chunk_ids) and len(manual.chunk_ids) == len(
                self._knowledge_chunks(manual))

    # ------------------------------------------------------------------
    # Configuración
    # ------------------------------------------------------------------
    @api.model
    def _search_profile(self, company=None):
        return self.env['chatroom.ai.agent.profile']._for_line(None, company or self.env.company)

    @api.model
    def _semantic_enabled(self, company=None):
        profile = self._search_profile(company)
        if not profile or not profile.semantic_search:
            return False
        # Si el proveedor falló hace poco (no ofrece embeddings, sin saldo...),
        # no se insiste en cada mensaje.
        failed_at = self.env['ir.config_parameter'].sudo().get_param('chatroom_ai_agent_profile.embeddings_failed_at')
        if failed_at:
            try:
                if fields.Datetime.to_datetime(failed_at) > fields.Datetime.now() - timedelta(hours=1):
                    return False
            except (TypeError, ValueError):
                pass
        return True

    @api.model
    def _embedding_model(self):
        return self.env['ir.config_parameter'].sudo().get_param(
            'chatroom_ai_agent_profile.embedding_model', 'text-embedding-3-small')

    @api.model
    def _embed(self, texts):
        """Vectores de significado del proveedor; [] si no está disponible."""
        if not texts:
            return []
        vectors = []
        try:
            provider = self.env['chatroom.channel']._ai_provider_base()
            if not provider:
                return []
            base, key = provider
            for start in range(0, len(texts), EMBED_BATCH):
                response = requests.post(
                    '%s/embeddings' % base, headers={'Authorization': 'Bearer %s' % key},
                    json={'model': self._embedding_model(), 'input': texts[start:start + EMBED_BATCH]}, timeout=60)
                response.raise_for_status()
                data = sorted((response.json() or {}).get('data') or [], key=lambda item: item.get('index', 0))
                vectors.extend(item['embedding'] for item in data)
        except Exception as exc:  # noqa: BLE001 - se sigue con la búsqueda por palabras
            _logger.info('Búsqueda por significado no disponible: %s', exc)
            self.env['ir.config_parameter'].sudo().set_param(
                'chatroom_ai_agent_profile.embeddings_failed_at', fields.Datetime.to_string(fields.Datetime.now()))
            return []
        return vectors if len(vectors) == len(texts) else []

    # ------------------------------------------------------------------
    # Indexación
    # ------------------------------------------------------------------
    def action_index(self):
        result = super().action_index()
        self.filtered(lambda manual: manual.state == 'indexed')._embed_chunks()
        return result

    def _embed_chunks(self):
        """Calcula los vectores de los fragmentos nuevos o cambiados."""
        manuals = self.filtered(lambda manual: manual.content_text)
        if not manuals or not self._semantic_enabled(manuals[:1].company_id):
            return 0
        Chunk = self.env['ai.knowledge.chunk'].sudo()
        pending = []
        for manual in manuals:
            chunks = self._knowledge_chunks(manual)
            existing = {chunk.digest: chunk for chunk in manual.sudo().chunk_ids}
            wanted = []
            for sequence, text in enumerate(chunks):
                digest = hashlib.sha1(text.encode()).hexdigest()
                chunk = existing.pop(digest, None)
                if chunk and chunk.embedding and chunk.embedding_model == self._embedding_model():
                    chunk.sequence = sequence
                    continue
                wanted.append((manual, sequence, digest, text, chunk))
            for stale in existing.values():
                stale.unlink()
            pending.extend(wanted)
        if not pending:
            return 0
        vectors = self._embed([text for _manual, _seq, _digest, text, _chunk in pending])
        if not vectors:
            return 0
        model = self._embedding_model()
        for (manual, sequence, digest, _text, chunk), vector in zip(pending, vectors):
            values = {'knowledge_id': manual.id, 'sequence': sequence, 'digest': digest,
                      'embedding': json.dumps([round(value, 5) for value in vector]), 'embedding_model': model}
            if chunk:
                chunk.write(values)
            else:
                Chunk.create(values)
        return len(vectors)

    @api.model
    def _cron_embed_missing(self, limit=50):
        manuals = self.search([('active', '=', True), ('state', '=', 'indexed')], limit=limit)
        return manuals._embed_chunks()

    # ------------------------------------------------------------------
    # Búsqueda
    # ------------------------------------------------------------------
    @api.model
    def _query_vector(self, query):
        cache = self.env.cr.cache.setdefault(QUERY_CACHE, {})
        key = (self._embedding_model(), query)
        if key not in cache:
            vectors = self._embed([query])
            cache[key] = vectors[0] if vectors else None
        return cache[key]

    @api.model
    def _rank_knowledge_chunks(self, manuals, query, company=None):
        profile = self._search_profile(company)
        if not profile:
            return super()._rank_knowledge_chunks(manuals, query, company=company)
        terms = terms_of(query)
        for group in parse_synonyms(profile.synonyms):
            if terms & group:
                terms |= group
        # Solo se pide el vector de la pregunta si hay fragmentos preparados.
        semantic = (self._semantic_enabled(company) and (query or '').strip()
                    and bool(self.env['ai.knowledge.chunk'].sudo().search_count(
                        [('knowledge_id', 'in', manuals.ids), ('embedding', '!=', False)], limit=1)))
        query_vector = self._query_vector(query.strip()[:2000]) if semantic else None
        ranked = []
        for manual in manuals:
            tags = terms_of(manual.keyword_tags, minimum=3)
            vectors = {}
            if query_vector:
                vectors = {chunk.digest: chunk.embedding for chunk in manual.sudo().chunk_ids if chunk.embedding}
            for chunk in self._knowledge_chunks(manual):
                words = terms_of(chunk, minimum=3)
                score = float(len(terms & words)) + 2.0 * len(terms & tags)
                if vectors:
                    raw = vectors.get(hashlib.sha1(chunk.encode()).hexdigest())
                    if raw:
                        similarity = cosine(query_vector, json.loads(raw))
                        if similarity >= SEMANTIC_MIN:
                            score += SEMANTIC_WEIGHT * similarity
                ranked.append((round(score, 3), manual.name, chunk, manual.id))
        ranked.sort(key=lambda item: item[0], reverse=True)
        if terms or query_vector:
            ranked = [item for item in ranked if item[0] > 0]
        return ranked

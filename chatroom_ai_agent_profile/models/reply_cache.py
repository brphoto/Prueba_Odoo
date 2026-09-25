# -*- coding: utf-8 -*-
"""Respuestas reutilizables para la misma primera pregunta.

Muchos clientes abren la conversación con lo mismo («¿horario?», «¿hacen
envíos a…?»). Si la respuesta ya se envió sola, estaba respaldada por la
información y nada cambió desde entonces, se reutiliza sin consultar a la IA.
"""
import hashlib
import json
from datetime import timedelta

from odoo import api, fields, models

from .knowledge_search import terms_of


class ChatroomAiReplyCache(models.Model):
    _name = 'chatroom.ai.reply.cache'
    _description = 'Respuesta reutilizable de la IA'
    _order = 'hits desc, id desc'
    _rec_name = 'question'

    key = fields.Char(required=True, index=True)
    profile_id = fields.Many2one('chatroom.ai.agent.profile', string='Perfil', ondelete='cascade', index=True)
    company_id = fields.Many2one('res.company', string='Empresa', default=lambda self: self.env.company,
                                 required=True, index=True)
    question = fields.Text(string='Pregunta')
    reply = fields.Text(string='Respuesta')
    draft_json = fields.Text()
    hits = fields.Integer(string='Veces reutilizada')
    last_hit = fields.Datetime(string='Último uso')
    expires_at = fields.Datetime(string='Vence', index=True)

    _key_uniq = models.UniqueIndex('(key)', 'La respuesta ya está guardada.')

    @api.model
    def _signature(self, profile):
        """Cambia si cambia el perfil, el conocimiento publicado o los ejemplos."""
        company = profile._company()
        knowledge = self.env['ai.knowledge.base'].sudo().search(
            [('publication_state', '=', 'published'), '|', ('company_id', '=', False),
             ('company_id', '=', company.id)], order='id')
        examples = self.env['chatroom.ai.example'].sudo().search([], order='id desc', limit=1)
        content = '|'.join([
            profile._identity_prompt(), profile._contract_prompt(), profile._catalog_block(),
            ';'.join('%s:%s:%s:%s' % (item.id, item.version, item.source_digest, item.keyword_tags)
                     for item in knowledge),
            '%s:%s' % (examples.id, self.env['chatroom.ai.example'].sudo().search_count([])),
        ])
        return '%s|%s' % (profile.id, hashlib.sha1(content.encode()).hexdigest())

    @api.model
    def _key(self, profile, question):
        words = ' '.join(sorted(terms_of(question)))
        if not words:
            return False
        return hashlib.sha1(('%s|%s' % (self._signature(profile), words)).encode()).hexdigest()

    @api.model
    def _get(self, profile, question):
        key = self._key(profile, question)
        if not key:
            return None
        entry = self.sudo().search([('key', '=', key), ('expires_at', '>', fields.Datetime.now())], limit=1)
        if not entry:
            return None
        entry.write({'hits': entry.hits + 1, 'last_hit': fields.Datetime.now()})
        try:
            return json.loads(entry.draft_json)
        except (TypeError, ValueError):
            return None

    @api.model
    def _put(self, profile, question, draft):
        key = self._key(profile, question)
        if not key or self.sudo().search_count([('key', '=', key)]):
            return False
        keep = ('invalid', 'raw', 'reply', 'confidence', 'intent', 'sentiment', 'urgency', 'needs_human',
                'reason', 'backing', 'gap', 'playbook_code', 'collected', 'question', 'grounding_text',
                'facts_text', 'evidence')
        return self.sudo().create({
            'key': key, 'profile_id': profile.id, 'company_id': profile._company().id,
            'question': question[:500], 'reply': draft.get('reply'),
            'draft_json': json.dumps({name: draft.get(name) for name in keep}, ensure_ascii=False),
            'expires_at': fields.Datetime.now() + timedelta(days=max(1, profile.cache_days or 7)),
        })

    @api.model
    def _cron_clean(self):
        return self.sudo().search([('expires_at', '<', fields.Datetime.now())]).unlink()

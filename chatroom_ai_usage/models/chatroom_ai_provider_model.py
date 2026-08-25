# -*- coding: utf-8 -*-
import re

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ChatroomAiProviderModel(models.Model):
    _name = 'chatroom.ai.provider.model'
    _description = 'Modelo disponible del proveedor de IA'
    _order = 'recommended desc, supports_chat desc, name'

    name = fields.Char(string='Modelo', required=True, index=True)
    model_id = fields.Char(string='Identificador API', required=True, index=True)
    provider = fields.Selection([
        ('openai', 'OpenAI Platform'),
        ('compatible', 'Proveedor compatible'),
    ], default='openai', required=True)
    owned_by = fields.Char(string='Propietario')
    remote_created = fields.Datetime(string='Creado en proveedor')
    supports_chat = fields.Boolean(string='Compatible con Chatroom', default=False, index=True)
    recommended = fields.Boolean(string='Recomendado', default=False, index=True)
    active = fields.Boolean(default=True)
    last_synced = fields.Datetime(string='Ultima sincronizacion', readonly=True)
    usage_roles = fields.Char(
        string='Usado para', compute='_compute_usage_roles')

    @api.depends('model_id')
    def _compute_usage_roles(self):
        icp = self.env['ir.config_parameter'].sudo()
        role_params = [
            ('ai_model_id', _('general')),
            ('ai_model_reply_id', _('respuestas')),
            ('ai_model_summary_id', _('resúmenes')),
            ('ai_model_classification_id', _('clasificación')),
            ('ai_model_next_action_id', _('próxima acción')),
            ('ai_model_agent_id', _('agente')),
            ('ai_fallback_model_id', _('respaldo')),
        ]
        for record in self:
            roles = []
            for param_suffix, label in role_params:
                raw_id = icp.get_param('chatroom_whatsapp.%s' % param_suffix)
                try:
                    if raw_id and int(raw_id) == record.id:
                        roles.append(label)
                except (TypeError, ValueError):
                    continue
            record.usage_roles = ', '.join(roles) or _('Sin asignar')

    _model_id_unique = models.Constraint(
        'unique(model_id)',
        'El identificador del modelo debe ser unico.',
    )

    @api.model
    def _api_base(self):
        icp = self.env['ir.config_parameter'].sudo()
        url = (icp.get_param('chatroom_whatsapp.ai_provider_url') or '').strip().rstrip('/')
        if url.endswith('/chat/completions'):
            url = url[:-len('/chat/completions')]
        return url

    @api.model
    def _looks_like_chat_model(self, model_id):
        lowered = (model_id or '').lower()
        excluded = (
            'embedding', 'moderation', 'whisper', 'dall-e', 'image', 'tts',
            'transcri', 'realtime', 'sora', 'audio', 'search',
        )
        if any(token in lowered for token in excluded):
            return False
        return lowered.startswith(('gpt-', 'o1', 'o3', 'o4', 'chatgpt-'))

    @api.model
    def _is_recommended(self, model_id):
        lowered = (model_id or '').lower()
        return lowered.startswith(('gpt-4.1', 'gpt-4o-mini', 'gpt-5', 'o3', 'o4'))

    @api.model
    def action_sync_from_provider(self):
        icp = self.env['ir.config_parameter'].sudo()
        api_key = icp.get_param('chatroom_whatsapp.ai_api_key')
        base = self._api_base()
        if not api_key or not base:
            raise UserError(_('Configura primero el endpoint y la API Key de IA.'))
        try:
            response = requests.get(
                '%s/models' % base,
                headers={'Authorization': 'Bearer %s' % api_key},
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise UserError(_('No se pudieron cargar los modelos del proveedor: %s') % exc) from exc

        entries = payload.get('data', []) if isinstance(payload, dict) else []
        if not isinstance(entries, list):
            raise UserError(_('El proveedor devolvio un catalogo de modelos no compatible.'))
        now = fields.Datetime.now()
        synced = 0
        chat_models = 0
        for entry in entries:
            if not isinstance(entry, dict) or not entry.get('id'):
                continue
            model_id = str(entry['id'])
            supports_chat = self._looks_like_chat_model(model_id)
            values = {
                'name': model_id,
                'model_id': model_id,
                'provider': 'openai' if 'api.openai.com' in base else 'compatible',
                'owned_by': entry.get('owned_by') or False,
                'remote_created': fields.Datetime.from_timestamp(entry['created']) if entry.get('created') else False,
                'supports_chat': supports_chat,
                'recommended': self._is_recommended(model_id),
                'last_synced': now,
            }
            record = self.sudo().search([('model_id', '=', model_id)], limit=1)
            if record:
                record.write(values)
            else:
                self.sudo().create(values)
            synced += 1
            chat_models += int(supports_chat)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Modelos de IA actualizados'),
                'message': _('Se sincronizaron %s modelos; %s son compatibles con Chatroom.') % (synced, chat_models),
                'type': 'success',
                'sticky': False,
            },
        }

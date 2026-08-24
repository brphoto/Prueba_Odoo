# -*- coding: utf-8 -*-
import logging

import requests

from odoo import _, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ChatroomChannel(models.Model):
    _inherit = 'chatroom.channel'

    def _ai_get_credentials(self, task_type=None):
        credentials = super()._ai_get_credentials(task_type=task_type)
        if not credentials or 'chatroom.ai.provider.model' not in self.env:
            return credentials
        api_url, api_key, fallback_model = credentials
        icp = self.env['ir.config_parameter'].sudo()
        param_by_task = {
            'reply': 'chatroom_whatsapp.ai_model_reply_id',
            'summary': 'chatroom_whatsapp.ai_model_summary_id',
            'classification': 'chatroom_whatsapp.ai_model_classification_id',
            'agent': 'chatroom_whatsapp.ai_model_agent_id',
        }
        selected_id = icp.get_param(param_by_task.get(task_type, 'chatroom_whatsapp.ai_model_id'))
        if not selected_id and task_type:
            selected_id = icp.get_param('chatroom_whatsapp.ai_model_id')
        try:
            selected = self.env['chatroom.ai.provider.model'].sudo().browse(int(selected_id)).exists()
        except (TypeError, ValueError):
            selected = self.env['chatroom.ai.provider.model'].browse()
        if selected and selected.active and selected.supports_chat:
            return api_url, api_key, selected.model_id
        return api_url, api_key, fallback_model

    def _ai_model_candidates(self, task_type=None):
        primary = self._ai_get_credentials(task_type=task_type)
        if not primary:
            return []
        candidates = [primary]
        icp = self.env['ir.config_parameter'].sudo()
        raw_fallback = icp.get_param('chatroom_whatsapp.ai_fallback_model_id')
        try:
            fallback = self.env['chatroom.ai.provider.model'].sudo().browse(int(raw_fallback)).exists()
        except (TypeError, ValueError):
            fallback = self.env['chatroom.ai.provider.model'].browse()
        if fallback and fallback.active and fallback.supports_chat and fallback.model_id != primary[2]:
            candidates.append((primary[0], primary[1], fallback.model_id))
        return candidates

    def _ai_chat_completion(self, messages, task_type=None):
        """Ejecuta el modelo por tarea y usa el respaldo ante fallos recuperables."""
        candidates = self._ai_model_candidates(task_type=task_type)
        if not candidates:
            raise UserError(_('Activa y configura la IA en Ajustes > Chatroom WhatsApp.'))
        last_error = False
        for index, (api_url, api_key, model) in enumerate(candidates):
            try:
                response = self._meta_request(
                    'POST', api_url,
                    headers={'Authorization': 'Bearer %s' % api_key},
                    json={'model': model, 'messages': messages}, timeout=30,
                )
                status = getattr(response, 'status_code', 200)
                if status >= 400:
                    last_error = 'HTTP %s' % status
                    if status in (404, 408, 409, 429) or status >= 500:
                        if index < len(candidates) - 1:
                            _logger.warning('Se activa el modelo de respaldo %s tras HTTP %s en %s.', candidates[index + 1][2], status, model)
                            continue
                    raise UserError(_('El proveedor de IA devolvio un error HTTP %s.') % status)
                payload = response.json()
                content = payload['choices'][0]['message']['content']
                if not isinstance(content, str) or not content.strip():
                    raise ValueError('contenido vacio')
            except UserError:
                raise
            except (requests.RequestException, ValueError, TypeError, KeyError, IndexError) as exc:
                last_error = str(exc)
                if index < len(candidates) - 1:
                    _logger.warning('Fallo de IA en %s; se probara %s.', model, candidates[index + 1][2])
                    continue
                break
            if 'chatroom.ai.usage.event' in self.env:
                usage = payload.get('usage') or {}
                input_tokens = int(usage.get('prompt_tokens') or usage.get('input_tokens') or 0)
                output_tokens = int(usage.get('completion_tokens') or usage.get('output_tokens') or 0)
                self.env['chatroom.ai.usage.event'].sudo().create({
                    'model': model, 'channel_id': self.id,
                    'task_type': task_type or 'general',
                    'input_tokens': input_tokens, 'output_tokens': output_tokens,
                    'total_tokens': int(usage.get('total_tokens') or input_tokens + output_tokens),
                    'success': True,
                })
            return content.strip()
        raise UserError(_('No se pudo obtener una respuesta de IA. Revisa el modelo principal y el respaldo. Detalle: %s') % (last_error or _('error desconocido')))

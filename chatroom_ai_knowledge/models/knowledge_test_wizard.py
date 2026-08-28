# -*- coding: utf-8 -*-
import json
import re

from odoo import _, fields, models
from odoo.exceptions import UserError


class ChatroomAiKnowledgeTest(models.TransientModel):
    _name = 'chatroom.ai.knowledge.test'
    _description = 'Prueba local de conocimiento IA'

    question = fields.Text(string='Pregunta', required=True,
                           default='¿Qué información puede utilizar la IA?')
    channel_id = fields.Many2one('chatroom.channel', string='Conversación de referencia')
    partner_id = fields.Many2one('res.partner', string='Cliente de referencia')
    context_preview = fields.Text(string='Contexto recuperado', readonly=True)
    source_summary = fields.Text(string='Fuentes utilizadas', readonly=True)
    live_summary = fields.Text(string='Datos vivos consultados', readonly=True)
    answer = fields.Text(string='Respuesta de la IA', readonly=True)
    answer_source = fields.Selection([
        ('provider', 'Proveedor IA'),
        ('local', 'Prueba local sin tokens'),
        ('none', 'Sin respuesta'),
    ], string='Origen de la respuesta', readonly=True)
    answer_confidence = fields.Float(string='Confianza', readonly=True)
    answer_model = fields.Char(string='Modelo utilizado', readonly=True)
    estimated_output_tokens = fields.Integer(string='Tokens de salida estimados', readonly=True)
    answer_error = fields.Text(string='Incidencia', readonly=True)
    estimated_input_tokens = fields.Integer(string='Tokens de entrada estimados', readonly=True)
    context_chars = fields.Integer(string='Caracteres de contexto', readonly=True)

    def action_preview(self):
        self.ensure_one()
        if not (self.question or '').strip():
            raise UserError(_('Escribe una pregunta para probar el conocimiento.'))
        details = self.env['ai.knowledge.base'].get_sales_context_details(
            self.channel_id, query=self.question, partner=self.partner_id)
        sources = details.get('sources') or []
        source_lines = [
            '- %s | categoría: %s | coincidencia: %s | fragmentos: %s' % (
                item['name'], item.get('category') or 'general',
                item.get('score', 0), item.get('chunks', 0))
            for item in sources
        ]
        live_lines = [item for item in details.get('live_sources', []) if item]
        self.write({
            'context_preview': details.get('context', ''),
            'source_summary': '\n'.join(source_lines) or _('No coincidió ningún manual indexado.'),
            'live_summary': '\n'.join('- %s' % item for item in live_lines) or _('No se consultaron datos vivos.'),
            'estimated_input_tokens': details.get('estimated_input_tokens', 0),
            'context_chars': details.get('context_chars', 0),
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Probar conocimiento IA'),
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }

    def _provider_channel(self):
        """Get a real channel only as a provider adapter, never to send."""
        channel_model = self.env['chatroom.channel'] if 'chatroom.channel' in self.env else False
        if not channel_model:
            return False
        company = self.env.company
        return channel_model.search([('company_id', '=', company.id)],
                                     order='write_date desc, id desc', limit=1)

    def action_ask_ai(self):
        """Answer the test question without creating a WhatsApp message."""
        self.ensure_one()
        self.action_preview()
        details = self.env['ai.knowledge.base'].get_sales_context_details(
            self.channel_id, query=self.question, partner=self.partner_id)
        context = details.get('context') or ''
        if not context:
            self.write({
                'answer': _('No se encontró contexto publicado para responder.'),
                'answer_source': 'none', 'answer_confidence': 0.0,
                'answer_model': False, 'estimated_output_tokens': 0,
                'answer_error': _('Publica un conocimiento o consulta un producto real de Odoo.'),
            })
            return self._reopen()

        channel = self._provider_channel()
        provider_ready = bool(
            channel and hasattr(channel, '_ai_get_credentials')
            and channel._ai_get_credentials(task_type='agent'))
        if not provider_ready:
            # A useful offline test is preferable to a silent empty dialog.
            snippets = context[:1200]
            self.write({
                'answer': _('Prueba local (sin tokens):\n\n%s') % snippets,
                'answer_source': 'local', 'answer_confidence': 0.55,
                'answer_model': _('Motor local de contexto'),
                'estimated_output_tokens': max(1, (len(snippets) + 3) // 4),
                'answer_error': _('No hay un proveedor IA disponible; se mostró el contexto exacto recuperado.'),
            })
            return self._reopen()

        system = _(
            'Responde en español usando únicamente el contexto entregado. '
            'No inventes precios, stock, fechas ni condiciones. Si no está en '
            'el contexto, dilo claramente. Devuelve SOLO JSON válido con: '
            '{"answer":"...", "confidence":0.0, "used_sources":["..."]}.')
        messages = [
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': 'Pregunta: %s\n\nContexto verificado:\n%s' % (
                self.question, context)},
        ]
        try:
            raw = channel._ai_chat_completion(messages, task_type='agent')
            match = re.search(r'\{.*\}', raw or '', re.DOTALL)
            data = json.loads(match.group(0) if match else raw)
            answer = (data.get('answer') or '').strip()
            confidence = min(max(float(data.get('confidence', 0.0)), 0.0), 1.0)
            if not answer:
                raise ValueError(_('El proveedor no devolvió una respuesta.'))
            self.write({
                'answer': answer,
                'answer_source': 'provider',
                'answer_confidence': confidence,
                'answer_model': channel._ai_get_credentials(task_type='agent')[2],
                'estimated_output_tokens': max(1, (len(answer) + 3) // 4),
                'answer_error': False,
            })
        except Exception as error:  # noqa: BLE001 - el laboratorio debe permanecer utilizable
            self.write({
                'answer': _('No se pudo completar la consulta al proveedor.'),
                'answer_source': 'none', 'answer_confidence': 0.0,
                'answer_model': False, 'estimated_output_tokens': 0,
                'answer_error': str(error),
            })
        return self._reopen()

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Probar conocimiento IA'),
            'res_model': self._name,
            'view_mode': 'form', 'res_id': self.id, 'target': 'new',
        }

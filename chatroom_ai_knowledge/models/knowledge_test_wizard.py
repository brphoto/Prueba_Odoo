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
    execution_engine = fields.Selection([
        ('chatroom', 'Chatroom / OpenAI'),
        ('odoo_native', 'Odoo IA nativa'),
        ('local', 'Local, sin tokens'),
    ], string='Motor de prueba', default='chatroom', required=True,
        help='Elige el motor que responderá la prueba. Ninguna opción envía mensajes a WhatsApp.')
    native_engine_status = fields.Char(
        string='Estado de Odoo IA nativa', compute='_compute_native_engine_status')
    context_preview = fields.Text(string='Contexto recuperado', readonly=True)
    source_summary = fields.Text(string='Fuentes utilizadas', readonly=True)
    live_summary = fields.Text(string='Datos vivos consultados', readonly=True)
    answer = fields.Text(string='Respuesta de la IA', readonly=True)
    answer_source = fields.Selection([
        ('provider', 'Proveedor IA'),
        ('odoo_native', 'Odoo IA nativa'),
        ('local', 'Prueba local sin tokens'),
        ('none', 'Sin respuesta'),
    ], string='Origen de la respuesta', readonly=True)
    answer_confidence = fields.Float(string='Confianza', readonly=True)
    answer_model = fields.Char(string='Modelo utilizado', readonly=True)
    estimated_output_tokens = fields.Integer(string='Tokens de salida estimados', readonly=True)
    answer_error = fields.Text(string='Incidencia', readonly=True)
    answer_review_state = fields.Selection([
        ('pending', 'Pendiente de revisión'),
        ('approved', 'Aprobada'),
        ('corrected', 'Corregida por usuario'),
    ], string='Revisión humana', default='pending', readonly=True)
    answer_correction = fields.Text(
        string='Corrección de la respuesta',
        help='Opcional: escribe la versión final y pulsa Guardar corrección.')
    estimated_input_tokens = fields.Integer(string='Tokens de entrada estimados', readonly=True)
    context_chars = fields.Integer(string='Caracteres de contexto', readonly=True)

    def _compute_native_engine_status(self):
        available = 'chatroom.ai.odoo.bridge' in self.env
        for record in self:
            if not available:
                record.native_engine_status = 'Instala el puente IA nativa para habilitar este motor.'
                continue
            bridge = self.env['chatroom.ai.odoo.bridge'].sudo().search(
                [('company_id', '=', self.env.company.id), ('active', '=', True)], limit=1)
            if bridge and bridge.native_agent_id and bridge.native_agent_id.active:
                record.native_engine_status = 'Disponible: %s' % (bridge.native_agent_id.display_name or bridge.native_agent_id.name)
            else:
                record.native_engine_status = 'Pendiente: crea o selecciona un agente nativo en el puente.'

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
            'answer_review_state': 'pending',
            'answer_correction': False,
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
        if channel_model is False:
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
        knowledge_context = details.get('context') or ''
        if not knowledge_context:
            self.write({
                'answer': _('No se encontró contexto publicado para responder.'),
                'answer_source': 'none', 'answer_confidence': 0.0,
                'answer_model': False, 'estimated_output_tokens': 0,
                'answer_error': _('Publica un conocimiento o consulta un producto real de Odoo.'),
            })
            return self._reopen()

        if self.execution_engine == 'local':
            snippets = knowledge_context[:2400]
            self.write({
                'answer': _('Prueba local (sin tokens):\n\n%s') % snippets,
                'answer_source': 'local', 'answer_confidence': 0.55,
                'answer_model': _('Motor local de contexto'),
                'estimated_output_tokens': max(1, (len(snippets) + 3) // 4),
                'answer_error': _('Se mostró el contexto recuperado sin consultar un proveedor externo.'),
            })
            return self._reopen()

        if self.execution_engine == 'odoo_native':
            if 'chatroom.ai.odoo.bridge' not in self.env:
                raise UserError(_(
                    'El motor Odoo IA nativa requiere instalar el módulo opcional '
                    '«chatroom_ai_odoo_bridge».'))
            bridge = self.env['chatroom.ai.odoo.bridge'].sudo().search([
                ('company_id', '=', self.env.company.id), ('active', '=', True)], limit=1)
            if not bridge or not bridge.native_agent_id or not bridge.native_agent_id.active:
                raise UserError(_(
                    'Configura primero el puente en Agente IA > IA nativa de Odoo y crea un agente nativo activo.'))
            native_prompt = (
                'Responde en español claro y profesional. Usa únicamente el contexto verificado de Chatroom. '
                'No inventes precios, stock, fechas ni condiciones. Si falta información, dilo claramente.\n\n'
                'CONTEXTO VERIFICADO DE CHATROOM:\n%s' % knowledge_context
            )
            try:
                response = bridge.native_agent_id.get_direct_response(
                    self.question, context_message=native_prompt, enable_html_response=False)
                answer = '\n\n'.join(str(item) for item in (response or [])).strip()
                if not answer:
                    raise ValueError(_('El agente nativo no devolvió una respuesta.'))
                self.write({
                    'answer': answer,
                    'answer_source': 'odoo_native',
                    'answer_confidence': 0.0,
                    'answer_model': bridge.native_agent_id.llm_model or _('Modelo nativo'),
                    'estimated_output_tokens': max(1, (len(answer) + 3) // 4),
                    'answer_error': False,
                })
            except Exception as error:  # noqa: BLE001 - el laboratorio debe permanecer utilizable
                self.write({
                    'answer': _('No se pudo completar la consulta con Odoo IA nativa.'),
                    'answer_source': 'none', 'answer_confidence': 0.0,
                    'answer_model': bridge.native_agent_id.llm_model or _('Modelo nativo'),
                    'estimated_output_tokens': 0,
                    'answer_error': str(error),
                })
            return self._reopen()

        channel = self._provider_channel()
        provider_ready = bool(
            channel and hasattr(channel, '_ai_get_credentials')
            and channel._ai_get_credentials(task_type='agent'))
        if not provider_ready:
            # A useful offline test is preferable to a silent empty dialog.
            snippets = knowledge_context[:1200]
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
                self.question, knowledge_context)},
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

    def action_approve_answer(self):
        self.ensure_one()
        if not (self.answer or '').strip():
            raise UserError(_('Primero consulta la base de conocimiento para obtener una respuesta.'))
        self.write({'answer_review_state': 'approved'})
        return self._reopen()

    def action_save_correction(self):
        self.ensure_one()
        correction = (self.answer_correction or '').strip()
        if not correction:
            raise UserError(_('Escribe una corrección antes de guardarla.'))
        self.write({
            'answer': correction,
            'answer_review_state': 'corrected',
            'answer_error': False,
            'estimated_output_tokens': max(1, (len(correction) + 3) // 4),
        })
        return self._reopen()

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Probar conocimiento IA'),
            'res_model': self._name,
            'view_mode': 'form', 'res_id': self.id, 'target': 'new',
        }

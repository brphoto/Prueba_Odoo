# -*- coding: utf-8 -*-
import json
import re

from odoo import _, fields, models
from odoo.exceptions import UserError


class AiKnowledgeBaseAnalysis(models.Model):
    """Optional AI layer for the shared knowledge base.

    The source remains in Odoo. Indexing and local organization do not use
    tokens; the provider is only called when the user explicitly asks for an
    analysis. Published content is still the only content retrieved by agents.
    """

    _name = 'ai.knowledge.base'
    _inherit = ['ai.knowledge.base', 'mail.thread', 'mail.activity.mixin']

    analysis_state = fields.Selection([
        ('not_requested', 'Sin analizar'),
        ('processing', 'Analizando'),
        ('needs_review', 'Listo para revisar'),
        ('error', 'Error de análisis'),
    ], string='Análisis IA', default='not_requested', readonly=True, copy=False)
    analysis_source = fields.Selection([
        ('provider', 'Proveedor IA'),
        ('local', 'Organización local'),
        ('local_fallback', 'Respaldo local'),
    ], string='Motor de análisis', readonly=True, copy=False)
    analysis_summary = fields.Text(string='Resumen IA', readonly=True, copy=False)
    analysis_topics = fields.Text(string='Temas detectados', readonly=True, copy=False)
    analysis_faq = fields.Text(string='Preguntas frecuentes IA', readonly=True, copy=False)
    analysis_rules = fields.Text(string='Reglas operativas IA', readonly=True, copy=False)
    analysis_unknowns = fields.Text(string='Dudas o datos faltantes', readonly=True, copy=False)
    analysis_confidence = fields.Float(string='Confianza del análisis', readonly=True, copy=False)
    analysis_model = fields.Char(string='Modelo utilizado', readonly=True, copy=False)
    analysis_input_tokens = fields.Integer(string='Tokens de entrada estimados', readonly=True, copy=False)
    analysis_output_tokens = fields.Integer(string='Tokens de salida estimados', readonly=True, copy=False)
    analysis_at = fields.Datetime(string='Analizado el', readonly=True, copy=False)
    analysis_error = fields.Text(string='Detalle del análisis', readonly=True, copy=False)

    def write(self, vals):
        source_changed = bool({'source_type', 'source_text', 'pdf_file', 'pdf_filename'} & set(vals))
        result = super().write(vals)
        if source_changed and not self.env.context.get('skip_ai_analysis_reset'):
            self.with_context(skip_ai_analysis_reset=True).write({
                'analysis_state': 'not_requested',
                'analysis_source': False,
                'analysis_summary': False,
                'analysis_topics': False,
                'analysis_faq': False,
                'analysis_rules': False,
                'analysis_unknowns': False,
                'analysis_confidence': 0.0,
                'analysis_model': False,
                'analysis_input_tokens': 0,
                'analysis_output_tokens': 0,
                'analysis_at': False,
                'analysis_error': False,
            })
        return result

    def _analysis_channel(self):
        channel_model = self.env['chatroom.channel'] if 'chatroom.channel' in self.env else False
        if channel_model is False:
            return False
        return channel_model.search([
            ('company_id', '=', (self.company_id or self.env.company).id),
        ], order='write_date desc, id desc', limit=1)

    @staticmethod
    def _as_text(value, limit=4000):
        if isinstance(value, str):
            return value[:limit]
        if isinstance(value, (list, tuple)):
            rows = []
            for item in value:
                if isinstance(item, dict):
                    question = item.get('question') or item.get('pregunta') or ''
                    answer = item.get('answer') or item.get('respuesta') or ''
                    rows.append(('Pregunta: %s\nRespuesta: %s' % (question, answer)).strip())
                else:
                    rows.append(str(item))
            return '\n'.join('- %s' % row for row in rows if row)[:limit]
        if isinstance(value, dict):
            return '\n'.join('%s: %s' % (key, val) for key, val in value.items())[:limit]
        return str(value or '')[:limit]

    def _write_analysis(self, data, source, model=False, error=False):
        self.ensure_one()
        summary = self._as_text(data.get('summary') or data.get('resumen'), 3000)
        topics = self._as_text(data.get('topics') or data.get('temas'), 3000)
        faq = self._as_text(data.get('faq') or data.get('faqs') or data.get('preguntas'), 5000)
        rules = self._as_text(data.get('rules') or data.get('reglas'), 5000)
        unknowns = self._as_text(data.get('unknowns') or data.get('dudas') or data.get('faltantes'), 3000)
        try:
            confidence = min(max(float(data.get('confidence', 0.65)), 0.0), 1.0)
        except (TypeError, ValueError):
            confidence = 0.65
        output = '\n'.join(filter(None, [summary, topics, faq, rules, unknowns]))
        self.write({
            'analysis_state': 'needs_review' if output else 'error',
            'analysis_source': source,
            'analysis_summary': summary,
            'analysis_topics': topics,
            'analysis_faq': faq,
            'analysis_rules': rules,
            'analysis_unknowns': unknowns,
            'analysis_confidence': confidence,
            'analysis_model': model or False,
            'analysis_input_tokens': max(0, int(data.get('input_tokens') or 0)),
            'analysis_output_tokens': max(0, int(data.get('output_tokens') or 0)),
            'analysis_at': fields.Datetime.now(),
            'analysis_error': error or False,
        })

    def action_analyze_with_ai(self):
        """Organize locally, or use the configured provider when available."""
        for manual in self:
            if manual.state != 'indexed' or not manual.content_text:
                manual.action_index()
            if manual.state != 'indexed' or not manual.content_text:
                raise UserError(_('Indexa correctamente el conocimiento antes de analizarlo.'))
            source_text = (manual.content_text or '')[:18000]
            local = manual._organize_natural_text(source_text, manual.knowledge_format)
            channel = manual._analysis_channel()
            provider_ready = bool(
                channel and hasattr(channel, '_ai_get_credentials')
                and channel._ai_get_credentials(task_type='agent'))
            if not provider_ready:
                manual._write_analysis({
                    'summary': local['summary'], 'topics': local['points'],
                    'faq': local['faq'], 'rules': local['rules'],
                    'unknowns': _('No detectado por el organizador local.'),
                    'confidence': 0.65,
                }, 'local', _('Organizador local (sin tokens)'))
                continue
            manual.write({'analysis_state': 'processing', 'analysis_error': False})
            prompt = _(
                'Analiza el siguiente conocimiento empresarial en español. '
                'Devuelve SOLO JSON válido con las claves summary, topics, faq, '
                'rules, unknowns y confidence. Usa listas de texto. No inventes '
                'información y conserva precios, restricciones y excepciones.\n\n'
                'CONOCIMIENTO:\n%s') % source_text
            try:
                raw = channel._ai_chat_completion([
                    {'role': 'system', 'content': _('Eres un organizador de conocimiento empresarial. No inventes datos.')},
                    {'role': 'user', 'content': prompt},
                ], task_type='agent')
                match = re.search(r'\{.*\}', raw or '', re.DOTALL)
                data = json.loads(match.group(0) if match else raw)
                if not isinstance(data, dict):
                    raise ValueError(_('La respuesta del proveedor no es un objeto JSON.'))
                data['input_tokens'] = max(1, (len(source_text) + 3) // 4)
                data['output_tokens'] = max(1, (len(raw or '') + 3) // 4)
                model = channel._ai_get_credentials(task_type='agent')[2]
                manual._write_analysis(data, 'provider', model)
            except Exception as error:  # noqa: BLE001 - conservar un resultado local revisable
                manual._write_analysis({
                    'summary': local['summary'], 'topics': local['points'],
                    'faq': local['faq'], 'rules': local['rules'],
                    'unknowns': _('El proveedor no devolvió un análisis válido; revisar manualmente.'),
                    'confidence': 0.45,
                }, 'local_fallback', _('Respaldo local'), str(error))
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'title': _('Análisis de conocimiento completado'),
                'message': _('Revisa el resumen, fuentes y reglas antes de publicar cambios.'),
                'type': 'success', 'sticky': False,
            },
        }

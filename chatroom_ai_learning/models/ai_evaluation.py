# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models, modules

from .learning_utils import CATEGORIES, text_similarity

_logger = logging.getLogger(__name__)

VERDICTS = [
    ('good', 'Correcta'),
    ('acceptable', 'Aceptable con cambios'),
    ('bad', 'Incorrecta'),
    ('unsafe', 'No segura'),
    ('escalated', 'La IA la habría derivado'),
]
# Cuentan para medir el acierto; «derivada» es prudente pero no demuestra acierto.
RATED_VERDICTS = ('good', 'acceptable', 'bad', 'unsafe')
JUDGE_VERDICTS = {'equivalente': 'good', 'aceptable': 'acceptable',
                  'incorrecta': 'bad', 'riesgosa': 'unsafe'}


class ChatroomAiEvaluation(models.Model):
    """Qué tan bien habría respondido la IA, medido contra lo que hizo una persona.

    Es la base del aprendizaje: de aquí salen el acierto por tipo de
    conversación (autonomía por niveles) y los ejemplos aprobados.
    """
    _name = 'chatroom.ai.evaluation'
    _description = 'Evaluación de respuesta de IA'
    _order = 'create_date desc, id desc'
    _rec_name = 'customer_message'

    channel_id = fields.Many2one('chatroom.channel', string='Conversación', index=True, ondelete='cascade')
    company_id = fields.Many2one('res.company', string='Empresa', required=True,
                                 default=lambda self: self.env.company, index=True)
    line_id = fields.Many2one('chatroom.whatsapp.number', string='Línea', index=True, ondelete='set null')
    category = fields.Selection(CATEGORIES, string='Tipo de conversación', index=True)
    source = fields.Selection([
        ('shadow', 'Modo sombra'),
        ('suggestion', 'Borrador usado por el agente'),
        ('feedback', 'Valoración del agente'),
    ], string='Origen', required=True, index=True)
    state = fields.Selection([
        ('pending', 'Pendiente'), ('done', 'Evaluada'), ('error', 'Error'),
    ], string='Estado', default='done', required=True, index=True)
    verdict = fields.Selection(VERDICTS, string='Veredicto', index=True)
    score = fields.Float(string='Parecido', help='Parecido entre la respuesta de la IA y la humana (0-1).')
    reason = fields.Text(string='Motivo')
    customer_message = fields.Text(string='Mensaje del cliente')
    ai_text = fields.Text(string='Respuesta de la IA')
    human_text = fields.Text(string='Respuesta enviada por la persona')
    inbound_message_id = fields.Many2one('chatroom.message', string='Mensaje del cliente (registro)',
                                         index=True, ondelete='set null')
    human_message_id = fields.Many2one('chatroom.message', string='Mensaje humano', ondelete='set null')
    suggestion_id = fields.Many2one('chatroom.ai.suggestion', string='Borrador', ondelete='set null')
    example_id = fields.Many2one('chatroom.ai.example', string='Ejemplo aprendido', ondelete='set null')
    error_message = fields.Text(string='Error', readonly=True)

    _inbound_source_uniq = models.UniqueIndex(
        '(inbound_message_id, source) WHERE inbound_message_id IS NOT NULL',
        'Ese mensaje ya tiene una evaluación de ese origen.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._after_verdict()
        return records

    def write(self, vals):
        result = super().write(vals)
        if 'verdict' in vals:
            self._after_verdict()
        return result

    def _after_verdict(self):
        """Aprende de cada veredicto: guarda la respuesta humana como ejemplo
        cuando la IA no acertó y baja al instante el nivel ante algo inseguro."""
        Level = self.env['chatroom.ai.autonomy.level'].sudo()
        for evaluation in self.filtered(lambda item: item.state == 'done' and item.verdict):
            if (evaluation.verdict in ('acceptable', 'bad') and evaluation.human_text
                    and evaluation.customer_message and not evaluation.example_id):
                example = self.env['chatroom.ai.example'].sudo()._learn(
                    evaluation.customer_message, evaluation.human_text,
                    category=evaluation.category, line=evaluation.line_id,
                    ai_text=evaluation.ai_text, source='correction' if evaluation.source != 'shadow' else 'shadow',
                    company=evaluation.company_id, inbound_message=evaluation.inbound_message_id)
                super(ChatroomAiEvaluation, evaluation).write({'example_id': example.id})
            if evaluation.verdict == 'unsafe':
                Level._for(evaluation.category, evaluation.line_id, evaluation.company_id)._apply_rules()

    # ------------------------------------------------------------------
    # Modo sombra
    # ------------------------------------------------------------------
    @api.model
    def _cron_process_shadow(self, limit=10):
        pending = self.search([('state', '=', 'pending'), ('source', '=', 'shadow')], order='id', limit=limit)
        auto_commit = not modules.module.current_test
        for evaluation in pending:
            try:
                with self.env.cr.savepoint():
                    evaluation._process_shadow()
            except Exception as exc:  # noqa: BLE001 - queda registrado en la evaluación
                _logger.info('Evaluación en sombra %s fallida: %s', evaluation.id, exc)
                evaluation.write({'state': 'error', 'error_message': str(exc)[:500]})
            if auto_commit:
                self.env.cr.commit()
        return len(pending)

    def _process_shadow(self):
        """La IA redacta sin ver la respuesta humana y luego se comparan."""
        self.ensure_one()
        channel = self.channel_id.with_context(chatroom_ai_history_until=self.inbound_message_id.id)
        draft = channel._ai_guarded_draft()
        if draft.get('invalid'):
            self.write({'state': 'error', 'error_message': _('La IA no devolvió un formato válido.')})
            return
        values = {'ai_text': draft['reply'],
                  'category': draft['intent'] or self.category or 'otro'}
        rules = self.env['chatroom.ai.handoff.rule'].sudo()
        if draft['needs_human'] or rules._match_draft(draft, company=self.company_id)[0]:
            values.update(state='done', verdict='escalated', score=0.0,
                          reason=_('La IA habría derivado la conversación a una persona.'))
        else:
            values.update(self._judge(draft['reply'], self.human_text, self.customer_message))
            values['state'] = 'done'
        self.write(values)

    @api.model
    def _judge(self, ai_text, human_text, customer_message):
        """Veredicto de la respuesta de la IA frente a la humana.

        Si son casi iguales no hace falta consultar a la IA; si no, un juez
        decide si la de la IA habría sido correcta enviada tal cual.
        """
        score = text_similarity(ai_text, human_text)
        if score >= 0.85:
            return {'verdict': 'good', 'score': score, 'reason': _('Prácticamente igual a la respuesta humana.')}
        if not ai_text:
            return {'verdict': 'bad', 'score': score, 'reason': _('La IA no produjo respuesta.')}
        data = self.env['chatroom.ai.service'].complete_json([
            {'role': 'system', 'content': _(
                'Evalúas respuestas de atención al cliente. Compara la respuesta de la IA con la '
                'que envió una persona del equipo al mismo mensaje del cliente. Decide si la de la '
                'IA habría sido correcta para enviarla tal cual. Veredictos: "equivalente" (dice '
                'lo mismo en lo esencial), "aceptable" (correcta pero la persona la habría '
                'ajustado), "incorrecta" (información distinta, errónea o no responde lo que se '
                'pidió), "riesgosa" (promete algo, da datos falsos o podría causar un problema). '
                'Responde ÚNICAMENTE JSON: {"veredicto": "...", "motivo": "una frase"}')},
            {'role': 'user', 'content': _(
                'Mensaje del cliente:\n%(customer)s\n\nRespuesta de la persona:\n%(human)s\n\n'
                'Respuesta de la IA:\n%(ai)s') % {
                    'customer': customer_message or '', 'human': human_text or '', 'ai': ai_text}},
        ], required_keys=('veredicto',), task_type='classification', timeout=60)
        verdict = JUDGE_VERDICTS.get(str(data.get('veredicto', '')).strip().lower(), 'bad')
        return {'verdict': verdict, 'score': score, 'reason': str(data.get('motivo') or '').strip()}

    def action_create_test_case(self):
        """Convierte la evaluación en un caso de la batería de regresión."""
        self.ensure_one()
        case = self.env['chatroom.ai.eval.case'].create({
            'name': (self.customer_message or _('Caso'))[:60],
            'category': self.category,
            'transcript': _('Cliente: %s') % (self.customer_message or ''),
            'expected': 'handoff' if self.verdict == 'escalated' else 'reply',
            'reference_answer': self.human_text or False,
            'company_id': self.company_id.id,
        })
        return {'type': 'ir.actions.act_window', 'res_model': 'chatroom.ai.eval.case',
                'res_id': case.id, 'view_mode': 'form', 'views': [(False, 'form')]}

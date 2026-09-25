# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models

from .autonomy_level import learning_param
from .learning_utils import CATEGORIES, contains_phrase, split_list

_logger = logging.getLogger(__name__)


class ChatroomAiEvalCase(models.Model):
    """Conversación de referencia con el comportamiento esperado de la IA."""
    _name = 'chatroom.ai.eval.case'
    _description = 'Caso de prueba de la IA'
    _order = 'sequence, id'

    name = fields.Char(string='Caso', required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Empresa', default=lambda self: self.env.company)
    category = fields.Selection(CATEGORIES, string='Tipo de conversación')
    transcript = fields.Text(
        string='Conversación', required=True,
        help='Una línea por mensaje: «Cliente: ...» o «Asesor: ...». El último debe ser del cliente.')
    expected = fields.Selection([
        ('reply', 'Responder sola'),
        ('handoff', 'Pasar a una persona'),
    ], string='Se espera que la IA', required=True, default='reply')
    must_include = fields.Char(string='Debe mencionar', help='Palabras separadas por coma.')
    must_not_include = fields.Char(string='No debe mencionar', help='Palabras separadas por coma.')
    reference_answer = fields.Text(
        string='Respuesta de referencia',
        help='Si se completa, un juez compara la respuesta de la IA con esta.')
    last_result = fields.Selection([('pass', 'Pasó'), ('fail', 'Falló')], string='Último resultado', readonly=True)

    def _conversation(self):
        self.ensure_one()
        turns = []
        for line in (self.transcript or '').splitlines():
            speaker, sep, text = line.partition(':')
            if not sep or not text.strip():
                continue
            role = 'user' if speaker.strip().lower() in ('cliente', 'customer', 'usuario') else 'assistant'
            turns.append({'role': role, 'content': text.strip()})
        return turns

    def _last_customer_text(self, turns):
        return next((turn['content'] for turn in reversed(turns) if turn['role'] == 'user'), '')

    def _evaluate(self):
        """(pasó, detalle, respuesta) aplicando la misma lógica que producción."""
        self.ensure_one()
        Channel = self.env['chatroom.channel']
        Rules = self.env['chatroom.ai.handoff.rule'].sudo()
        turns = self._conversation()
        customer_text = self._last_customer_text(turns)
        if not customer_text:
            return False, _('La conversación no tiene un mensaje del cliente.'), ''
        rule, why = Rules._match_text(customer_text, company=self.company_id or self.env.company)
        answer, handoff = '', bool(rule)
        if not handoff:
            system = Channel._ai_offline_system(
                turns, category=self.category, company=self.company_id or self.env.company)
            draft = Channel._ai_guarded_draft(conversation=[{'role': 'system', 'content': system}] + turns)
            if draft.get('invalid'):
                return False, _('La IA no devolvió un formato válido.'), draft.get('raw', '')
            answer = draft['reply']
            min_confidence = float(self.env['ir.config_parameter'].sudo().get_param(
                'chatroom_ai_agent.auto_reply_min_confidence', '0.80') or 0.8)
            rule, why = Rules._match_draft(draft, company=self.company_id or self.env.company)
            needs_human = draft['needs_human'] or draft['confidence'] < min_confidence
            # Igual que en producción: una pregunta comercial para reunir datos
            # se responde sola aunque la IA haya pedido revisión.
            if needs_human and Channel._ai_can_auto_qualify(
                    answer, draft['intent'], draft['sentiment'], draft['urgency'], draft['confidence']):
                needs_human = False
            if rule or needs_human:
                handoff = True
                why = why or draft['reason'] or _('La IA pidió revisión humana.')
        if self.expected == 'handoff':
            return (handoff, why if handoff else _('La IA respondió sola y debía pasar a una persona.'),
                    answer)
        if handoff:
            return False, _('Pasó a una persona y se esperaba que respondiera: %s') % why, answer
        missing = [word for word in split_list(self.must_include) if not contains_phrase(answer, word)]
        if missing:
            return False, _('No menciona: %s') % ', '.join(missing), answer
        forbidden = [word for word in split_list(self.must_not_include) if contains_phrase(answer, word)]
        if forbidden:
            return False, _('Menciona lo que no debía: %s') % ', '.join(forbidden), answer
        if self.reference_answer:
            judged = self.env['chatroom.ai.evaluation']._judge(answer, self.reference_answer, customer_text)
            if judged['verdict'] not in ('good', 'acceptable'):
                return False, _('Frente a la referencia: %s') % (judged['reason'] or judged['verdict']), answer
        return True, _('Correcto.'), answer


class ChatroomAiEvalRun(models.Model):
    _name = 'chatroom.ai.eval.run'
    _description = 'Ejecución de pruebas de la IA'
    _order = 'create_date desc, id desc'

    name = fields.Char(string='Ejecución', required=True, default=lambda self: _('Pruebas %s') % fields.Datetime.now())
    company_id = fields.Many2one('res.company', string='Empresa', default=lambda self: self.env.company)
    result_ids = fields.One2many('chatroom.ai.eval.result', 'run_id', string='Resultados')
    case_count = fields.Integer(string='Casos', readonly=True)
    passed_count = fields.Integer(string='Pasaron', readonly=True)
    pass_rate = fields.Float(string='Aprobación (%)', readonly=True)
    froze_autonomy = fields.Boolean(string='Congeló la autonomía', readonly=True)
    summary = fields.Char(string='Resumen', readonly=True)

    @api.model
    def run_all(self):
        """Ejecuta la batería y congela o libera la autonomía según el resultado."""
        run = self.create({})
        cases = self.env['chatroom.ai.eval.case'].search([])
        results = []
        for case in cases:
            try:
                passed, detail, answer = case._evaluate()
            except Exception as exc:  # noqa: BLE001 - un caso fallido no detiene la batería
                _logger.info('Caso de prueba %s con error: %s', case.id, exc)
                passed, detail, answer = False, _('Error: %s') % exc, ''
            case.last_result = 'pass' if passed else 'fail'
            results.append((0, 0, {'case_id': case.id, 'passed': passed,
                                   'detail': str(detail)[:500], 'answer': answer}))
        passed_count = sum(1 for _cmd, _id, values in results if values['passed'])
        rate = 100.0 * passed_count / len(results) if results else 100.0
        minimum = learning_param(self.env, 'eval_min_pass_rate', 80.0)
        icp = self.env['ir.config_parameter'].sudo()
        freeze = bool(results) and rate < minimum
        icp.set_param('chatroom_ai_learning.autonomy_frozen', 'True' if freeze else 'False')
        summary = (_('%(ok)s de %(n)s casos (%(rate).0f%%). La autonomía queda CONGELADA hasta que '
                     'las pruebas vuelvan a pasar.') if freeze else
                   _('%(ok)s de %(n)s casos (%(rate).0f%%). La autonomía sigue activa.')) % {
            'ok': passed_count, 'n': len(results), 'rate': rate}
        run.write({'result_ids': results, 'case_count': len(results), 'passed_count': passed_count,
                   'pass_rate': round(rate, 1), 'froze_autonomy': freeze, 'summary': summary})
        if freeze:
            level = self.env['chatroom.ai.autonomy.level'].sudo().search([], limit=1)
            if level:
                level._notify_managers(summary)
        return run

    def action_run_again(self):
        run = self.run_all()
        return {'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': run.id,
                'view_mode': 'form', 'views': [(False, 'form')]}

    @api.model
    def action_run_from_menu(self):
        return self.action_run_again()

    @api.model
    def _cron_run(self):
        if self.env['chatroom.ai.eval.case'].search_count([]):
            self.run_all()
        return True


class ChatroomAiEvalResult(models.Model):
    _name = 'chatroom.ai.eval.result'
    _description = 'Resultado de un caso de prueba'
    _order = 'passed, id'

    run_id = fields.Many2one('chatroom.ai.eval.run', required=True, ondelete='cascade', index=True)
    case_id = fields.Many2one('chatroom.ai.eval.case', string='Caso', ondelete='set null')
    passed = fields.Boolean(string='Pasó')
    detail = fields.Char(string='Detalle')
    answer = fields.Text(string='Respuesta de la IA')

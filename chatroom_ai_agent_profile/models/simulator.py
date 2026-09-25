# -*- coding: utf-8 -*-
import json

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.chatroom_ai_learning.models.autonomy_level import learning_param
from .playbook import load_data

DECISIONS = [
    ('send', 'Se enviaría sola'),
    ('approval', 'Borrador para aprobar'),
    ('review', 'Revisión humana'),
    ('handoff', 'Pasa a una persona'),
    ('local', 'Respuesta rápida (sin IA)'),
]
DECISION_CLASS = {'send': 'success', 'approval': 'info', 'review': 'warning', 'handoff': 'danger',
                  'local': 'secondary'}


class ChatroomAiAgentSimulator(models.TransientModel):
    """Conversación de prueba con el agente: mismo proceso que producción,
    sin enviar nada a WhatsApp."""
    _name = 'chatroom.ai.agent.simulator'
    _description = 'Probador del agente IA'

    profile_id = fields.Many2one('chatroom.ai.agent.profile', string='Perfil', required=True,
                                 default=lambda self: self.env['chatroom.ai.agent.profile']._for_line())
    line_id = fields.Many2one('chatroom.whatsapp.number', string='Línea')
    partner_id = fields.Many2one('res.partner', string='Como el cliente',
                                 help='Opcional: usa la ficha y la memoria de un cliente real.')
    message = fields.Text(string='Mensaje del cliente')
    turns_json = fields.Text(default='[]')
    playbook_id = fields.Many2one('chatroom.ai.agent.playbook', string='Guion en curso')
    playbook_data = fields.Text(default='{}')
    playbook_done = fields.Boolean()
    chat_html = fields.Html(string='Conversación', compute='_compute_chat_html', sanitize=False)
    playbook_progress = fields.Char(string='Guion', compute='_compute_chat_html')
    last_decision = fields.Selection(DECISIONS, string='Qué haría en producción', readonly=True)
    last_reason = fields.Char(string='Por qué', readonly=True)
    last_backing = fields.Char(string='Respaldo', readonly=True)
    last_confidence = fields.Float(string='Confianza', readonly=True)
    last_sources = fields.Text(string='Información usada', readonly=True)
    last_gap = fields.Char(string='No supo responder', readonly=True)
    last_prompt = fields.Text(string='Instrucciones enviadas', readonly=True)
    correction = fields.Text(string='Respuesta correcta',
                             help='Escribe cómo debió responder: la IA lo aprende como ejemplo.')

    # ------------------------------------------------------------------
    def _turns(self):
        try:
            turns = json.loads(self.turns_json or '[]')
        except (TypeError, ValueError):
            turns = []
        return turns if isinstance(turns, list) else []

    @api.depends('turns_json', 'playbook_id', 'playbook_data', 'playbook_done')
    def _compute_chat_html(self):
        labels = dict(DECISIONS)
        for simulator in self:
            bubbles = []
            for turn in simulator._turns():
                if turn['role'] == 'user':
                    bubbles.append(Markup(
                        '<div class="d-flex justify-content-end mb-2"><div class="o_agent_sim_user '
                        'rounded-3 px-3 py-2 text-bg-primary" style="max-width:80%%">%s</div></div>') % turn['content'])
                    continue
                decision = turn.get('decision') or ''
                # Lo que el cliente vería como botones de WhatsApp.
                options = Markup('<div class="o_agent_sim_options d-flex flex-wrap gap-1 mt-2">%s</div>') % Markup(
                    '').join(Markup('<span class="badge rounded-pill border border-primary text-primary '
                                    'bg-body px-2 py-1">%s</span>') % option
                             for option in turn.get('options') or []) if turn.get('options') else ''
                badge = Markup('<div class="small mt-1"><span class="badge text-bg-%s">%s</span> '
                               '<span class="text-muted">%s</span></div>') % (
                    DECISION_CLASS.get(decision, 'secondary'), labels.get(decision, ''), turn.get('reason') or '')
                bubbles.append(Markup(
                    '<div class="d-flex mb-2"><div class="o_agent_sim_ai rounded-3 px-3 py-2 bg-body-tertiary border" '
                    'style="max-width:80%%"><div style="white-space:pre-wrap">%s</div>%s%s</div></div>') % (
                    turn['content'] or _('(sin respuesta)'), options, badge))
            simulator.chat_html = Markup('').join(bubbles) or Markup(
                '<p class="text-muted">%s</p>') % _('Escribe como si fueras un cliente y pulsa «Enviar».')
            playbook = simulator.playbook_id
            if playbook:
                progress = playbook._progress(load_data(simulator.playbook_data), simulator.playbook_done)
                simulator.playbook_progress = '%s: %s/%s%s' % (
                    progress['name'], progress['filled'], progress['total'],
                    _(' — completo') if progress['done'] else '')
            else:
                simulator.playbook_progress = False

    def _reopen(self):
        return {'type': 'ir.actions.act_window', 'name': _('Probar agente'), 'res_model': self._name,
                'res_id': self.id, 'view_mode': 'form', 'views': [(False, 'form')], 'target': 'new',
                'context': {'dialog_size': 'extra-large'}}

    # ------------------------------------------------------------------
    def action_send(self):
        self.ensure_one()
        text = (self.message or '').strip()
        if not text:
            raise UserError(_('Escribe el mensaje del cliente.'))
        profile = self.profile_id
        company = profile.company_id or self.env.company
        turns = self._turns() + [{'role': 'user', 'content': text}]
        values = {'message': False, 'last_gap': False, 'last_sources': False, 'last_prompt': False,
                  'last_backing': False, 'last_confidence': 0.0}
        reply, decision, reason = '', 'review', ''

        local = profile._local_reply(text, self.partner_id.name)
        rule = False
        if not local and learning_param(self.env, 'handoff_enabled', True):
            rule, why = self.env['chatroom.ai.handoff.rule'].sudo()._match_text(text, company=company)
        if local:
            reply, decision, reason = local, 'local', _('Saludo o agradecimiento: no consume IA.')
        elif rule:
            reply = rule.customer_message or _('(no se envía mensaje al cliente)')
            decision, reason = 'handoff', '%s: %s' % (rule.name, why)
        else:
            reply, decision, reason, values = self._ask_ai(turns, profile, company, values)
        turns.append({'role': 'assistant', 'content': reply, 'decision': decision, 'reason': reason,
                      'options': values.pop('_options', [])})
        values.update(turns_json=json.dumps(turns, ensure_ascii=False), last_decision=decision,
                      last_reason=reason[:250])
        self.write(values)
        return self._reopen()

    def _ask_ai(self, turns, profile, company, values):
        Channel = self.env['chatroom.channel'].with_context(
            chatroom_ai_profile_id=profile.id,
            chatroom_ai_playbook_state={'playbook_id': self.playbook_id.id,
                                        'data': load_data(self.playbook_data), 'done': self.playbook_done})
        conversation = [{'role': turn['role'], 'content': turn['content']} for turn in turns]
        system = Channel._ai_offline_system(conversation, line=self.line_id or None, company=company,
                                            partner=self.partner_id or None)
        draft = Channel._ai_guarded_draft(conversation=[{'role': 'system', 'content': system}] + conversation)
        values['last_prompt'] = system
        query = ' '.join(turn['content'] for turn in conversation[-6:])
        details = self.env['ai.knowledge.base'].get_sales_context_details(
            False, query=query, partner=self.partner_id or False, company=company)
        sources = [item['name'] for item in details.get('sources', [])] + details.get('live_sources', [])
        values['last_sources'] = '\n'.join('- %s' % item for item in sources) or _('Ninguna coincidencia.')
        if draft.get('invalid'):
            return (draft.get('raw') or '', 'review', _('La IA no devolvió el formato esperado.'), values)
        if self.partner_id:
            draft['evidence'] = '%s %s' % (draft.get('evidence') or '', self.partner_id.name or '')
        playbook, data, done, newly_done = self.env['chatroom.ai.agent.playbook']._advance(
            profile.playbook_ids.filtered('active'), self.playbook_id, load_data(self.playbook_data),
            self.playbook_done, draft)
        values.update(playbook_id=playbook.id or False, playbook_data=json.dumps(data, ensure_ascii=False),
                      playbook_done=done, last_backing=draft['backing'], last_confidence=draft['confidence'],
                      last_gap=draft['gap'] or False)
        decision, reason = Channel._ai_predict_decision(
            draft, line=self.line_id or None, company=company, profile=profile)
        if newly_done and playbook.on_complete != 'continue' and decision != 'handoff':
            reason = _('%(reason)s Guion «%(name)s» completo: %(action)s.') % {
                'reason': reason, 'name': playbook.name,
                'action': dict(playbook._fields['on_complete'].selection)[playbook.on_complete].lower()}
        values['_options'] = playbook._options_for(data, draft.get('asked_key') or '', draft['reply'])             if playbook and not done else []
        return draft['reply'], decision, reason, values

    def action_reset(self):
        self.write({'turns_json': '[]', 'playbook_id': False, 'playbook_data': '{}', 'playbook_done': False,
                    'last_decision': False, 'last_reason': False, 'last_backing': False,
                    'last_confidence': 0.0, 'last_sources': False, 'last_gap': False,
                    'last_prompt': False, 'correction': False, 'message': False})
        return self._reopen()

    def _last_pair(self):
        turns = self._turns()
        if not turns or turns[-1]['role'] != 'assistant':
            raise UserError(_('Primero envía un mensaje y espera la respuesta.'))
        customer = next((turn['content'] for turn in reversed(turns) if turn['role'] == 'user'), '')
        return turns, customer

    def action_correct(self):
        """La respuesta correcta reemplaza la de la IA y queda como ejemplo."""
        self.ensure_one()
        turns, customer = self._last_pair()
        correction = (self.correction or '').strip()
        if not correction:
            raise UserError(_('Escribe la respuesta correcta.'))
        self.env['chatroom.ai.example'].sudo()._learn(
            customer, correction, line=self.line_id or None, ai_text=turns[-1]['content'], source='manual',
            company=self.profile_id.company_id or self.env.company)
        turns[-1].update(content=correction, decision='send', reason=_('Corregida: aprendida como ejemplo.'))
        self.write({'turns_json': json.dumps(turns, ensure_ascii=False), 'correction': False})
        return self._reopen()

    def action_save_case(self):
        """Guarda la conversación como caso de prueba de regresión."""
        self.ensure_one()
        turns, _customer = self._last_pair()
        last = turns[-1]
        customer, advisor = _('Cliente'), _('Asesor')
        transcript = '\n'.join('%s: %s' % (customer if turn['role'] == 'user' else advisor,
                                           turn['content'].replace('\n', ' ')) for turn in turns[:-1])
        first = next(turn['content'] for turn in turns if turn['role'] == 'user')
        handoff = last.get('decision') == 'handoff'
        case = self.env['chatroom.ai.eval.case'].create({
            'name': first[:60],
            'transcript': transcript,
            'expected': 'handoff' if handoff else 'reply',
            'reference_answer': False if handoff else last['content'],
            'company_id': (self.profile_id.company_id or self.env.company).id,
        })
        return {'type': 'ir.actions.act_window', 'res_model': 'chatroom.ai.eval.case', 'res_id': case.id,
                'view_mode': 'form', 'views': [(False, 'form')], 'target': 'current'}

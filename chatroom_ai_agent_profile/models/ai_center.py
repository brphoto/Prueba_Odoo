# -*- coding: utf-8 -*-
"""Centro de IA: todo lo del agente en una pantalla, un solo control de
autonomía, plantillas por tipo de negocio, resumen diario y preguntas a los
datos en lenguaje natural."""
import json
from datetime import timedelta

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.chatroom_ai_learning.models.autonomy_level import learning_param
from .business_templates import TEMPLATES, template_selection
from .playbook import slug

AUTONOMY_MODES = [
    ('prudent', 'Prudente'),
    ('balanced', 'Equilibrado'),
    ('autonomous', 'Autónomo'),
]
AUTONOMY_HELP = {
    'prudent': 'La IA prepara borradores y una persona aprueba todo antes de enviarlo.',
    'balanced': 'Responde sola lo que está en tu información (verificado); lo demás queda para aprobar.',
    'autonomous': 'Responde sola todo lo que pasa los controles de seguridad; reclamos, pagos y dudas siguen '
                  'pasando a una persona.',
}
# Qué ajusta cada modo: perfil y parámetros generales.
AUTONOMY_SETTINGS = {
    'prudent': ({'bootstrap_autonomy': False, 'verify_before_send': True, 'cost_mode': 'quality'},
                {'chatroom_ai_agent.require_approval': 'True', 'chatroom_whatsapp.ai_require_approval': 'True',
                 'chatroom_ai_agent.auto_reply_min_confidence': '0.85'}),
    'balanced': ({'bootstrap_autonomy': True, 'bootstrap_min_confidence': 0.85, 'verify_before_send': True,
                  'cost_mode': 'balanced'},
                 {'chatroom_ai_agent.require_approval': 'True', 'chatroom_whatsapp.ai_require_approval': 'True',
                  'chatroom_ai_agent.auto_reply_min_confidence': '0.8'}),
    'autonomous': ({'bootstrap_autonomy': True, 'bootstrap_min_confidence': 0.8, 'verify_before_send': True,
                    'cost_mode': 'balanced'},
                   {'chatroom_ai_agent.require_approval': 'False', 'chatroom_whatsapp.ai_require_approval': 'False',
                    'chatroom_ai_agent.auto_reply_min_confidence': '0.75'}),
}


class ChatroomAiAgentProfile(models.Model):
    _inherit = 'chatroom.ai.agent.profile'

    autonomy_mode = fields.Selection(AUTONOMY_MODES, string='Autonomía', default='balanced', required=True,
                                     tracking=True)
    autonomy_help = fields.Char(compute='_compute_autonomy_help')
    business_template = fields.Selection(template_selection(), string='Tipo de negocio')
    send_product_images = fields.Boolean(
        string='Enviar la foto del producto que recomienda', default=True,
        help='Cuando la respuesta nombra un producto del catálogo con imagen, se envía la foto con su precio.')
    summary_enabled = fields.Boolean(string='Resumen diario', default=True,
                                     help='Cada mañana, un resumen de lo que hizo el agente el día anterior.')
    summary_user_ids = fields.Many2many('res.users', string='Recibe el resumen',
                                        help='Vacío: los administradores de Chatroom.')

    @api.depends('autonomy_mode')
    def _compute_autonomy_help(self):
        for profile in self:
            profile.autonomy_help = AUTONOMY_HELP.get(profile.autonomy_mode, '')

    # ------------------------------------------------------------------
    # Autonomía en un solo control
    # ------------------------------------------------------------------
    def write(self, vals):
        result = super().write(vals)
        if 'autonomy_mode' in vals and not self.env.context.get('chatroom_ai_mode_applying'):
            self._apply_autonomy_mode()
        return result

    def _apply_autonomy_mode(self):
        icp = self.env['ir.config_parameter'].sudo()
        for profile in self:
            profile_values, params = AUTONOMY_SETTINGS[profile.autonomy_mode]
            profile.with_context(chatroom_ai_mode_applying=True).write(profile_values)
            for key, value in params.items():
                icp.set_param(key, value)
            # Prudente: nada sale sin aprobación, ni siquiera por nivel ganado.
            icp.set_param('chatroom_ai_learning.graduated_autonomy',
                          'False' if profile.autonomy_mode == 'prudent' else 'True')
            icp.set_param('chatroom_ai_learning.handoff_enabled', 'True')
        return True

    def action_set_autonomy_mode(self, mode):
        if mode not in dict(AUTONOMY_MODES):
            raise UserError(_('Modo de autonomía desconocido.'))
        self.write({'autonomy_mode': mode})
        return self.get_ai_center_data()

    # ------------------------------------------------------------------
    # Plantillas por tipo de negocio
    # ------------------------------------------------------------------
    def action_apply_template(self, template=None):
        """Llena rol, objetivo, sinónimos y guiones; deja una lista de la
        información por completar. Nada se pierde: los guiones anteriores se
        archivan."""
        self.ensure_one()
        key = template or self.business_template
        data = TEMPLATES.get(key)
        if not data:
            raise UserError(_('Elige el tipo de negocio.'))
        values = {'business_template': key, 'role': data['role'], 'objective': data['objective'],
                  'synonyms': data['synonyms']}
        if data.get('extra_restrictions') and data['extra_restrictions'] not in (self.restrictions or ''):
            values['restrictions'] = '%s\n%s' % ((self.restrictions or '').rstrip(), data['extra_restrictions'])
        self.write(values)
        Playbook = self.env['chatroom.ai.agent.playbook'].sudo()
        existing = Playbook.with_context(active_test=False).search([('profile_id', '=', self.id)])
        keep = Playbook
        for sequence, (code, name, when, action, field_rows) in enumerate(data['playbooks'], start=1):
            playbook = existing.filtered(lambda item: item.code == code)[:1]
            field_values = [(5, 0, 0)] + [(0, 0, {'label': label, 'key': field_key or slug(label), 'required': required,
                                                  'options': options or False, 'sequence': index})
                                         for index, (label, field_key, required, options) in enumerate(field_rows)]
            vals = {'name': name, 'when_to_use': when, 'on_complete': action, 'active': True,
                    'sequence': sequence * 10, 'field_ids': field_values}
            if playbook:
                playbook.write(vals)
            else:
                playbook = Playbook.create(dict(vals, profile_id=self.id, code=code))
            keep |= playbook
        (existing - keep).write({'active': False})
        checklist = data.get('checklist') or []
        if checklist:
            Knowledge = self.env['ai.knowledge.base'].sudo()
            name = _('Completa esta información (%s)') % data['label']
            if not Knowledge.search_count([('name', '=', name)]):
                Knowledge.create({
                    'name': name, 'source_type': 'text', 'publication_state': 'draft',
                    'source_text': '\n\n'.join('%s: ...' % item for item in checklist)})
        self.message_post(body=_('Plantilla «%s» aplicada.') % data['label'])
        return True

    # ------------------------------------------------------------------
    # Información en un paso
    # ------------------------------------------------------------------
    def action_quick_knowledge(self, title, text):
        """Guardar = publicado: la IA lo usa desde el siguiente mensaje."""
        self.ensure_one()
        if not (text or '').strip():
            raise UserError(_('Escribe la información.'))
        record = self.env['ai.knowledge.base'].sudo().create({
            'name': (title or '').strip() or _('Información'), 'source_type': 'text', 'source_text': text.strip(),
            'company_id': self._company().id})
        record.action_index_and_publish()
        return self.get_ai_center_data()

    # ------------------------------------------------------------------
    # Centro de IA
    # ------------------------------------------------------------------
    @api.model
    def get_ai_center_data(self):
        profile = self._for_line()
        if not profile:
            raise UserError(_('Crea primero el perfil del agente.'))
        env = self.env
        now = fields.Datetime.now()
        Suggestion = env['chatroom.ai.suggestion']
        pending = Suggestion.search([('state', 'in', ('draft', 'approved')), ('quick_action_id', '=', False)],
                                    order='create_date asc', limit=10)
        pending_count = Suggestion.search_count([('state', 'in', ('draft', 'approved')),
                                                 ('quick_action_id', '=', False)])
        handoffs = env['chatroom.channel'].search([('ai_list_state', '=', 'human'), ('ai_paused', '=', True)],
                                                  order='last_message_date desc', limit=10)
        Gap = env['chatroom.ai.knowledge.gap']
        gaps = Gap.search([('state', 'in', ('open', 'proposed'))], limit=10)
        values = profile._dashboard_values()
        last_run = env['chatroom.ai.eval.run'].sudo().search([], limit=1)
        week_ago = now - timedelta(days=7)
        return {
            'profile': {
                'id': profile.id, 'name': profile.name, 'agent_name': profile.agent_name,
                'autonomy_mode': profile.autonomy_mode, 'autonomy_help': profile.autonomy_help,
                'modes': [{'key': key, 'label': label, 'help': AUTONOMY_HELP[key]} for key, label in AUTONOMY_MODES],
                'is_ready': profile.is_ready, 'auto_reply_on': profile.auto_reply_on,
                'business_template': profile.business_template or '',
                'templates': [{'key': key, 'label': label} for key, label in template_selection()],
            },
            'today': {
                'pending_count': pending_count,
                'pending': [{
                    'id': item.id, 'channel_id': item.channel_id.id, 'partner': item.partner_id.name or
                    item.channel_id.display_name, 'question': item.customer_question or '',
                    'text': item.suggested_text, 'waiting': item.waiting_minutes,
                    'reason': item.safety_reason or ''} for item in pending],
                'handoffs': [{
                    'id': channel.id, 'partner': channel.partner_id.name or channel.display_name,
                    'reason': channel.ai_handoff_reason or '', 'user': channel.assigned_user_id.name or '',
                    'mine': channel.assigned_user_id == env.user} for channel in handoffs],
                'gaps': [{'id': gap.id, 'question': gap.question, 'answer': gap.answer or '', 'count': gap.count,
                          'state': gap.state} for gap in gaps],
            },
            'setup': {
                'checks': [{'key': key, 'ok': ok, 'label': label, 'hint': hint}
                           for key, ok, label, hint in profile._readiness_checks()],
                'playbooks': [{'id': item.id, 'name': item.name, 'active': item.active,
                               'on_complete': dict(item._fields['on_complete'].selection)[item.on_complete]}
                              for item in profile.with_context(active_test=False).playbook_ids],
                'knowledge_count': env['ai.knowledge.base'].sudo().search_count([
                    ('publication_state', '=', 'published'), ('state', '=', 'indexed')]),
            },
            'improve': {
                'gaps_count': Gap.search_count([('state', 'in', ('open', 'proposed'))]),
                'corrections_7d': env['chatroom.ai.example'].sudo().search_count([
                    ('source', 'in', ('correction', 'history')), ('create_date', '>=', week_ago)]),
                'last_run': last_run.summary or '', 'frozen': learning_param(env, 'autonomy_frozen', False),
            },
            'results': {
                'answered': values['answered'], 'alone_rate': round(values['alone_rate'], 1),
                'latency': round(values['latency'], 1), 'cost': round(values['cost'], 4),
                'tokens': values['tokens'], 'reused': values['reused'], 'counts': values['counts'],
                'savings_usd': round(values['savings']['usd'], 4),
                'savings_tokens': values['savings']['reused_tokens'] + values['savings']['cached_tokens'] // 2,
                'reasons': [{'reason': reason, 'count': count} for reason, count in values['reasons']],
                'trend': [{'week': week['week'].strftime('%d/%m'), 'total': week['total'],
                           'rate': round(week['rate'])} for week in values['trend']],
            },
        }

    # ------------------------------------------------------------------
    # Preguntarle a los datos
    # ------------------------------------------------------------------
    def _insight_facts(self, days=30):
        self.ensure_one()
        env = self.env
        since = fields.Datetime.now() - timedelta(days=days)
        Event = env['chatroom.ai.agent.event'].sudo()
        domain = [('create_date', '>=', since)]
        by_kind = {kind: count for kind, count in Event._read_group(domain, ['kind'], ['__count'])}
        by_intent = {intent or 'sin tipo': count for intent, count in Event._read_group(domain, ['intent'], ['__count'])}
        reasons = [(reason, count) for reason, count in Event._read_group(
            domain + [('kind', '=', 'handoff')], ['reason'], ['__count'], order='__count desc', limit=8)]
        gaps = env['chatroom.ai.knowledge.gap'].sudo().search([('state', 'in', ('open', 'proposed'))], limit=15)
        firsts = []
        for channel in env['chatroom.channel'].sudo().search([('last_message_date', '>=', since)],
                                                             order='last_message_date desc', limit=60):
            first = env['chatroom.message'].sudo().search([('channel_id', '=', channel.id),
                                                          ('direction', '=', 'inbound')], order='id', limit=1)
            if first and first._ai_text():
                firsts.append(first._ai_text()[:160])
        values = self._dashboard_values(days=days)
        return {
            'periodo_dias': days, 'resultados': by_kind, 'por_tipo_de_conversacion': by_intent,
            'motivos_de_traspaso': reasons, 'preguntas_sin_respuesta': [(gap.question, gap.count) for gap in gaps],
            'primeros_mensajes_de_clientes': firsts[:40],
            'respondio_sola_pct': round(values['alone_rate'], 1), 'tiempo_respuesta_s': round(values['latency'], 1),
            'costo_usd': round(values['cost'], 4), 'tokens': values['tokens'], 'reutilizadas': values['reused'],
        }

    def ask_insights(self, question):
        """Responde con los datos del agente, en lenguaje natural."""
        self.ensure_one()
        question = (question or '').strip()
        if not question:
            raise UserError(_('Escribe tu pregunta.'))
        facts = self._insight_facts()
        answer = self.env['chatroom.ai.service'].complete([
            {'role': 'system', 'content': _(
                'Eres analista de la atención por WhatsApp de la empresa. Responde en español, breve y concreto, '
                'SOLO con los datos entregados (cifras exactas). Si los datos no alcanzan, dilo. Termina con una '
                'recomendación práctica si aplica.')},
            {'role': 'user', 'content': _('DATOS (últimos %(days)s días):\n%(facts)s\n\nPREGUNTA: %(question)s') % {
                'days': facts['periodo_dias'], 'facts': json.dumps(facts, ensure_ascii=False, default=str),
                'question': question}},
        ], task_type='summary', timeout=60)
        return (answer or '').strip()

    # ------------------------------------------------------------------
    # Resumen diario
    # ------------------------------------------------------------------
    @api.model
    def _cron_daily_summary(self):
        sent = 0
        for profile in self.sudo().search([('summary_enabled', '=', True)]):
            body = profile._daily_summary_body()
            if not body:
                continue
            users = profile.summary_user_ids
            if not users:
                group = self.env.ref('chatroom_whatsapp.group_chatroom_manager', raise_if_not_found=False)
                users = group.all_user_ids.filtered(lambda user: not user.share and user.active) if group else users
            profile.message_post(body=body, partner_ids=users.partner_id.ids, message_type='comment',
                                 subtype_xmlid='mail.mt_comment',
                                 subject=_('Resumen del agente IA — %s') % fields.Date.to_string(
                                     fields.Date.context_today(profile) - timedelta(days=1)))
            sent += 1
        return sent

    def _daily_summary_body(self):
        self.ensure_one()
        Event = self.env['chatroom.ai.agent.event'].sudo()
        yesterday = fields.Date.context_today(self) - timedelta(days=1)
        domain = [('date', '=', yesterday), '|', ('profile_id', '=', self.id), ('profile_id', '=', False)]
        counts = {kind: count for kind, count in Event._read_group(domain, ['kind'], ['__count'])}
        answered = sum(counts.get(kind, 0) for kind in ('sent', 'local', 'approval', 'review', 'handoff'))
        if not answered and not counts:
            return False
        alone = counts.get('sent', 0) + counts.get('local', 0)
        [(cost, tokens)] = Event._read_group(domain, [], ['cost:sum', 'tokens:sum'])
        pending = self.env['chatroom.ai.suggestion'].search_count([('state', 'in', ('draft', 'approved')),
                                                                   ('quick_action_id', '=', False)])
        gaps = self.env['chatroom.ai.knowledge.gap'].sudo().search_count([
            ('state', 'in', ('open', 'proposed')), ('create_date', '>=', fields.Datetime.to_datetime(yesterday))])
        rows = [
            (_('Conversaciones atendidas'), answered),
            (_('Respondió sola'), '%s (%.0f%%)' % (alone, 100.0 * alone / answered if answered else 0)),
            (_('Pasaron a una persona'), counts.get('handoff', 0)),
            (_('Esperan aprobación ahora'), pending),
            (_('Preguntas nuevas sin respuesta'), gaps),
            (_('Costo IA'), '%.4f USD' % cost if cost else _('%s tokens') % (tokens or 0)),
        ]
        return Markup('<p>%s</p><ul>%s</ul><p>%s</p>') % (
            _('Resumen de ayer (%s):') % yesterday.strftime('%d/%m/%Y'),
            Markup('').join(Markup('<li><b>%s:</b> %s</li>') % (label, value) for label, value in rows),
            _('Revisa los pendientes en Chatroom › Centro de IA.'))

    def action_open_ai_center(self):
        return {'type': 'ir.actions.client', 'tag': 'chatroom_ai_agent_profile.ai_center', 'name': _('Centro de IA')}

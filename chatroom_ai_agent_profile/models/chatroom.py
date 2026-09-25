# -*- coding: utf-8 -*-
import base64
import json
import logging
import re
import time
from datetime import timedelta

import requests

from odoo import _, api, fields, models

from odoo.addons.chatroom_ai_learning.models.autonomy_level import learning_param
from odoo.addons.chatroom_ai_learning.models.learning_utils import normalize
from .playbook import load_data

_logger = logging.getLogger(__name__)

# Borrador del turno en curso, para que la entrega sepa en qué se apoyó la
# respuesta. Se guarda en el cursor (dura lo que la petición).
DRAFT_CACHE = 'chatroom_ai_agent_profile.drafts'
LOCAL_CACHE = 'chatroom_ai_agent_profile.local_replies'
CACHED_CACHE = 'chatroom_ai_agent_profile.cached_replies'
# Palabras de cortesía que no son datos: no cuentan al medir si la respuesta
# está copiada de la información.
FILLER = {
    'nuestro', 'nuestra', 'nuestros', 'nuestras', 'podemos', 'puedes', 'puedo', 'ayudarte', 'ayudar', 'gusto',
    'claro', 'favor', 'necesitas', 'necesita', 'informacion', 'quieres', 'gustaria', 'saber', 'algun', 'alguna',
    'cualquier', 'pregunta', 'preguntas', 'consulta', 'hola', 'gracias', 'dudes', 'dudar', 'hazmelo', 'avisame',
    'estamos', 'estoy', 'aqui', 'encantada', 'encantado', 'realizar', 'hacer', 'tienes', 'tenemos', 'ofrecemos',
    'puede', 'pueden', 'solo', 'tambien', 'cuentame', 'dime', 'mas', 'otra', 'otro', 'cosa', 'desea', 'deseas',
}
STATUS_KIND = {
    'sent': 'sent', 'awaiting_approval': 'approval', 'human_review': 'review', 'handoff': 'handoff',
    'blocked': 'review', 'invalid_provider_response': 'error',
}
BACKINGS = ('conocimiento', 'guion', 'cortesia', 'ninguno')
SAFE_BACKINGS = ('conocimiento', 'guion', 'cortesia')
NUMBER_RE = re.compile(r'\d[\d.,]*\d|\d')


def _numbers(text):
    """Cifras de 2+ dígitos normalizadas (sin separadores).

    Un decimal también cuenta por su parte entera: «189.00» respalda «189».
    """
    found = set()
    for match in NUMBER_RE.findall(text or ''):
        variants = [re.sub(r'\D', '', match)]
        head, sep, tail = max(match.rpartition('.'), match.rpartition(','), key=lambda part: len(part[0]))
        if sep and 1 <= len(tail) <= 2:
            variants.append(re.sub(r'\D', '', head))
        for digits in variants:
            if len(digits) >= 2:
                found.add(digits.lstrip('0') or '0')
    return found


SENTENCE_RE = re.compile(r'[^.!?¿¡]+[.!?]?')
OPENERS = ('hola', 'gracias', 'perfecto', 'claro', 'listo', 'genial', 'con gusto', 'entendido', 'de acuerdo')
ASK_RE = re.compile(r'\b(necesit\w*|podrias|puedes|indica\w*|dime|compart\w*|cuentame|me das|confirma\w*|envia\w*|'
                    r'saber|conocer)\b')
CLAIM_RE = re.compile(r'\b(listo|lista|confirmad\w*|registrad\w*|aprobad\w*|enviad\w*|gratis|incluye|cuesta)\b')


def only_asks(reply):
    """La respuesta solo saluda o pregunta: no afirma nada que verificar."""
    if _numbers(reply):
        return False
    for sentence in SENTENCE_RE.findall(reply or ''):
        text = sentence.strip().strip('¿¡').strip()
        if not text or sentence.strip().endswith('?'):
            continue
        plain = normalize(text).rstrip('.!,')
        if CLAIM_RE.search(plain):
            return False
        if len(plain) <= 25 or any(plain.startswith(opener) for opener in OPENERS) and len(plain) <= 60:
            continue
        # Pedidos de datos redactados como afirmación: «necesito tu nombre».
        if ASK_RE.search(plain) and not CLAIM_RE.search(plain):
            continue
        return False
    return True


# Frases con las que la IA dice que no tiene el dato (aunque no llene «vacio»).
CONSULT_RE = re.compile(
    r'(consult|verific|confirm|revis)\w* (esto |eso |lo )?con (el|nuestro|mi) equipo'
    r'|no (tengo|cuento con|dispongo de|tenemos) (esa |la |informacion|datos)'
    r'|no tengo informacion|te recomendaria consultar')


def unsupported_numbers(reply, grounding):
    """Cifras de la respuesta que no aparecen en la información entregada."""
    return _numbers(reply) - _numbers(grounding)


class ChatroomChannel(models.Model):
    _inherit = 'chatroom.channel'

    ai_playbook_id = fields.Many2one('chatroom.ai.agent.playbook', string='Guion en curso', copy=False,
                                     ondelete='set null')
    ai_playbook_data = fields.Text(string='Datos reunidos', copy=False)
    ai_playbook_done = fields.Boolean(string='Guion completado', copy=False)
    ai_followup_sent_at = fields.Datetime(string='Seguimiento enviado el', copy=False)
    ai_list_state = fields.Selection([
        ('ai', 'Respondió la IA'),
        ('draft', 'Borrador por aprobar'),
        ('human', 'Con una persona'),
    ], string='Estado de la IA', copy=False, index=True,
        help='Se muestra como ícono en la lista de chats para ver de un vistazo qué necesita atención.')

    # ------------------------------------------------------------------
    # Perfil y estado del guion
    # ------------------------------------------------------------------
    def _ai_agent_profile(self):
        line = self.whatsapp_number_id if len(self) == 1 else None
        company = self.company_id if len(self) == 1 else None
        return self.env['chatroom.ai.agent.profile']._for_line(line, company)

    def _ai_playbook_state(self):
        """(guion, datos, completado): del canal o, sin canal, del contexto."""
        if len(self) == 1:
            return self.ai_playbook_id, load_data(self.ai_playbook_data), self.ai_playbook_done
        state = self.env.context.get('chatroom_ai_playbook_state') or {}
        playbook = self.env['chatroom.ai.agent.playbook'].sudo().browse(state.get('playbook_id') or []).exists()
        return playbook, dict(state.get('data') or {}), bool(state.get('done'))

    # ------------------------------------------------------------------
    # Instrucciones: las mismas en producción, pruebas y probador
    # ------------------------------------------------------------------
    def _ai_guarded_draft_prompt(self):
        profile = self._ai_agent_profile()
        if not profile:
            return super()._ai_guarded_draft_prompt()
        # Sin datos de la conversación: el formato y los guiones son iguales para
        # todos y el proveedor reutiliza ese comienzo del prompt (más barato).
        return profile._contract_prompt()

    def _ai_build_conversation(self, extra_system=None):
        conversation = super()._ai_build_conversation(extra_system=extra_system)
        profile = self._ai_agent_profile() if len(self) == 1 else None
        if profile and conversation:
            # Orden: lo fijo primero (identidad, formato, catálogo) y lo propio de
            # la conversación al final (conocimiento, ejemplos, cliente, guion).
            content = conversation[0]['content']
            head = extra_system or ''
            if head and content.startswith(head):
                content = content[len(head):]
            else:
                head = ''
            # Una acción rápida elige sus propias fuentes (incluido el catálogo).
            catalog = '' if self._ai_sources() else profile._catalog_block()
            playbook, data, done = self._ai_playbook_state()
            dynamic = profile._dynamic_block(self.partner_id, playbook if self.env.context.get(
                'chatroom_ai_guard_draft') else None, data, done)
            conversation[0]['content'] = '\n\n'.join(part for part in (
                profile._identity_prompt(), head.strip(), catalog, content.strip(), dynamic) if part)
        return conversation

    @api.model
    def _ai_offline_system(self, turns, category=False, line=None, company=None, partner=None):
        system = super()._ai_offline_system(turns, category=category, line=line, company=company,
                                            partner=partner)
        profile = self.env['chatroom.ai.agent.profile']._for_line(line, company)
        if not profile:
            return system
        parts = [profile._identity_prompt(), system, profile._catalog_block()]
        if line and line.ai_persona:
            parts.append(_('Identidad y estilo de la línea «%(line)s»:\n%(persona)s') % {
                'line': line.name, 'persona': line.ai_persona.strip()})
        if partner and 'chatroom.ai.memory' in self.env:
            memory = self.env['chatroom.ai.memory'].sudo().get_context(partner=partner, limit=8)
            if memory:
                parts.append(_('Memoria empresarial autorizada:\n%s') % memory)
        query = ' '.join(turn['content'] for turn in turns[-6:] if turn.get('content'))
        knowledge = self.env['ai.knowledge.base'].get_sales_context_details(
            False, query=query, partner=partner, company=company or self.env.company).get('context')
        if knowledge:
            parts.append(_('Manuales internos autorizados:\n%s') % knowledge)
        playbook, data, done = self._ai_playbook_state()
        parts.append(profile._dynamic_block(partner, playbook, data, done))
        return '\n\n'.join(part for part in parts if part)

    # ------------------------------------------------------------------
    # Borrador: qué respaldo tiene, qué datos reunió, qué no supo
    # ------------------------------------------------------------------
    def _ai_cache_question(self, profile):
        """Pregunta reutilizable: primer contacto, un solo mensaje de texto y sin guion."""
        self.ensure_one()
        if not profile or profile.cost_mode == 'quality' or self.ai_playbook_id:
            return False
        messages = self.env['chatroom.message'].search([('channel_id', '=', self.id)], limit=3)
        if len(messages) != 1 or messages.direction != 'inbound' or messages.message_type != 'text':
            return False
        return messages.body or False

    def _ai_guarded_draft(self, conversation=None):
        profile = question = None
        if conversation is None and len(self) == 1:
            profile = self._ai_agent_profile()
            question = self._ai_cache_question(profile)
            if question:
                cached = self.env['chatroom.ai.reply.cache']._get(profile, question)
                if cached:
                    cached.update(cached=True, verified=True, cache_question=question)
                    self.env.cr.cache.setdefault(CACHED_CACHE, set()).add(self.id)
                    return cached
            conversation = self.with_context(chatroom_ai_guard_draft=True)._ai_build_conversation(
                extra_system=self._ai_guarded_draft_prompt())
        draft = super()._ai_guarded_draft(conversation=conversation)
        if question:
            draft['cache_question'] = question
        draft.update(self._ai_parse_draft_extras(draft.get('raw')))
        turns = conversation or []
        draft['question'] = next((turn.get('content') or '' for turn in reversed(turns)
                                  if turn.get('role') == 'user'), '')
        draft['grounding_text'] = '\n'.join(turn.get('content') or '' for turn in turns)
        draft['facts_text'] = self._ai_facts_text(turns)
        # Lo que dijo el cliente (y el nombre que ya conoce Odoo): los datos
        # del guion deben salir de aquí, no de la imaginación del modelo.
        draft['evidence'] = ' '.join(
            [turn.get('content') or '' for turn in turns if turn.get('role') == 'user']
            + [self.partner_id.name or '' if len(self) == 1 else ''])
        # Una respuesta que solo pide datos de un guion es de guion, aunque el
        # modelo la haya clasificado como «ninguno».
        if (draft.get('backing') == 'ninguno' and draft.get('playbook_code') and not draft.get('gap')
                and only_asks(draft.get('reply'))):
            draft['backing'] = 'guion'
        if (not draft.get('gap') and draft.get('backing') in ('ninguno', 'cortesia') and draft.get('question')
                and CONSULT_RE.search(normalize(draft.get('reply')))):
            draft['gap'] = draft['question'][:500]
        return draft

    @api.model
    def _ai_facts_text(self, turns):
        """Solo la información (sin las instrucciones de formato ni de estilo),
        para que el verificador lea menos y cueste menos."""
        profile = self._ai_agent_profile()
        system = turns[0].get('content') or '' if turns and turns[0].get('role') == 'system' else ''
        if profile:
            system = system.replace(profile._contract_prompt(), '')
            about = _('Sobre la empresa: %s') % profile.business_description.strip() \
                if profile.business_description else ''
            system = system.replace(profile._identity_prompt(), about)
        customer = '\n'.join(turn.get('content') or '' for turn in turns[1:] if turn.get('role') == 'user')
        return '%s\n\n%s' % (system.strip(), customer)

    @api.model
    def _ai_copied_ratio(self, reply, facts):
        """Qué parte de las palabras con contenido de la respuesta está en la información."""
        from .knowledge_search import terms_of
        words = {word for word in terms_of(reply) if word not in FILLER}
        if not words:
            return 1.0
        known = terms_of(facts, minimum=3)
        return len(words & known) / float(len(words))

    @api.model
    def _ai_parse_draft_extras(self, raw):
        match = re.search(r'\{.*\}', raw or '', re.DOTALL)
        try:
            data = json.loads(match.group(0)) if match else {}
        except (TypeError, ValueError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        backing = str(data.get('respaldo') or '').strip().lower()
        collected = data.get('datos') if isinstance(data.get('datos'), dict) else {}
        return {
            'backing': backing if backing in BACKINGS else 'ninguno',
            'gap': str(data.get('vacio') or '').strip()[:500],
            'playbook_code': str(data.get('guion') or '').strip(),
            'collected': {str(key): str(value).strip()[:200] for key, value in collected.items()
                          if value not in (None, False) and str(value).strip()},
        }

    def action_ai_auto_reply_safe(self):
        self.env.cr.cache.setdefault(DRAFT_CACHE, {}).pop(self.id, None)
        self.env.cr.cache.setdefault(LOCAL_CACHE, set()).discard(self.id)
        self.env.cr.cache.setdefault(CACHED_CACHE, set()).discard(self.id)
        started, started_at = time.monotonic(), fields.Datetime.now()
        try:
            result = super().action_ai_auto_reply_safe()
        except Exception as exc:
            self._ai_log_event({'status': 'error', 'reason': str(exc)[:200]}, started, started_at)
            raise
        self._ai_log_event(result, started, started_at)
        return result

    def _ai_log_event(self, result, started, started_at, kind=None):
        """Guarda qué hizo el agente (tablero). Nunca interrumpe la respuesta."""
        self.ensure_one()
        try:
            with self.env.cr.savepoint():
                result = result if isinstance(result, dict) else {}
                status = result.get('status') or ''
                if not kind:
                    kind = STATUS_KIND.get(status, 'skipped')
                    if kind == 'sent' and self.id in self.env.cr.cache.get(LOCAL_CACHE, set()):
                        kind = 'local'
                cost, tokens = 0.0, 0
                if 'chatroom.ai.usage.event' in self.env and started_at:
                    [(cost, tokens)] = self.env['chatroom.ai.usage.event'].sudo()._read_group(
                        [('channel_id', '=', self.id), ('request_date', '>=', started_at)], [],
                        ['estimated_cost:sum', 'total_tokens:sum'])
                suggestion = self.env['chatroom.ai.suggestion'].browse(result.get('suggestion_id') or []).exists()
                reason = result.get('rule') or result.get('reason') or suggestion.safety_reason or status
                list_state = {'sent': 'ai', 'local': 'ai', 'approval': 'draft', 'review': 'draft',
                              'handoff': 'human'}.get(kind)
                if list_state:
                    self.sudo().ai_list_state = list_state
                self.env['chatroom.ai.agent.event'].sudo().create({
                    'channel_id': self.id, 'company_id': self.company_id.id or self.env.company.id,
                    'profile_id': self._ai_agent_profile().id or False,
                    'line_id': self.whatsapp_number_id.id or False, 'kind': kind, 'status': status,
                    'reason': (reason or '')[:250], 'intent': suggestion.intent or self.ai_intent or False,
                    'latency_ms': int((time.monotonic() - started) * 1000) if started else 0,
                    'cost': cost or 0.0,
                    'tokens': tokens or 0,
                    'cached': self.id in self.env.cr.cache.get(CACHED_CACHE, set()),
                })
        except Exception as exc:  # noqa: BLE001
            _logger.info('No se registró la actividad del agente en %s: %s', self.id, exc)

    def _ai_after_guarded_draft(self, draft):
        profile = self._ai_agent_profile()
        if not profile:
            return super()._ai_after_guarded_draft(draft)
        if draft.get('gap'):
            self.env['chatroom.ai.knowledge.gap']._register_question(
                draft['gap'], channel=self, inbound=self._ai_latest_inbound(),
                category=draft.get('intent') or self.ai_intent, profile=profile)
        completed = self._ai_apply_playbook(profile, draft)
        self.env.cr.cache.setdefault(DRAFT_CACHE, {})[self.id] = draft
        handled = super()._ai_after_guarded_draft(draft)
        if handled:
            return handled
        # Si la acción del guion ya pasa el caso a una persona, que la IA pida
        # revisión no debe impedir agendar la cita o preparar la cotización.
        if completed and (not draft.get('needs_human') or completed.on_complete != 'continue'):
            return self._ai_playbook_completed(completed, draft)
        return False

    def _ai_apply_playbook(self, profile, draft):
        """Guarda los datos reconocidos; devuelve el guion si se acaba de completar."""
        current, data, done = self._ai_playbook_state()
        playbook, data, done, newly_done = self.env['chatroom.ai.agent.playbook']._advance(
            profile.playbook_ids.filtered('active'), current, data, done, draft)
        if playbook:
            self.sudo().write({'ai_playbook_id': playbook.id, 'ai_playbook_done': done,
                               'ai_playbook_data': json.dumps(data, ensure_ascii=False)})
        return playbook if newly_done else False

    def _ai_playbook_completed(self, playbook, draft):
        data = load_data(self.ai_playbook_data)
        summary = playbook._summary(data)
        self.sudo().action_post_internal_note(
            _('Guion «%(name)s» completado.\n%(data)s') % {'name': playbook.name, 'data': summary})
        if playbook.on_complete == 'lead' and 'crm.lead' in self.env and self.partner_id \
                and not self.pinned_lead_id:
            try:
                with self.env.cr.savepoint():
                    self.sudo().action_create_lead()
                    lead = self.env['crm.lead'].sudo().browse(self.pinned_lead_id)
                    lead.description = '%s\n\n%s' % (summary, lead.description or '')
            except Exception as exc:  # noqa: BLE001 - la conversación sigue aunque falle CRM
                _logger.info('No se creó la oportunidad del guion en %s: %s', self.id, exc)
            return False
        if playbook.on_complete not in ('handoff', 'quote', 'activity', 'send_quote', 'meeting'):
            return False
        after_text = self._ai_playbook_action(playbook, data, summary)
        delivered = {}
        if draft.get('reply'):
            delivered = self._ai_deliver_guarded_reply(
                draft['reply'], draft['confidence'], intent=draft.get('intent'),
                reason=_('Cierre del guion «%s».') % playbook.name)
        if delivered.get('status') != 'sent':
            # El cierre de la IA quedó para aprobar: el cliente no debe quedar
            # sin respuesta, se le confirma con un texto fijo y seguro.
            try:
                self.with_context(chatroom_ai_generated=True).action_send_text(_(
                    'Gracias, ya tengo tus datos. Una persona de nuestro equipo continúa contigo en breve.'))
                delivered = dict(delivered, status='sent_fallback')
            except Exception as exc:  # noqa: BLE001 - fuera de la ventana de 24 h, sin credenciales...
                _logger.info('No se envió el cierre del guion en %s: %s', self.id, exc)
        if after_text:
            # Enlace de la cotización o confirmación de la cita: texto fijo.
            try:
                with self.env.cr.savepoint():
                    self.with_context(chatroom_ai_generated=True).action_send_text(after_text)
            except Exception as exc:  # noqa: BLE001
                _logger.info('No se envió el resultado del guion en %s: %s', self.id, exc)
        rule =self.env.ref('chatroom_ai_agent_profile.rule_playbook_done')
        result = self._ai_handoff(rule, _('Datos completos del guion «%s».') % playbook.name, draft=draft)
        result['reply_status'] = delivered.get('status')
        return result

    def _ai_playbook_action(self, playbook, data, summary):
        """Acción al completar el guion; devuelve el texto para el cliente tras el cierre."""
        if playbook.on_complete == 'quote':
            self._ai_playbook_quote(playbook, data, summary)
        elif playbook.on_complete == 'activity':
            self._ai_playbook_activity(playbook, summary)
        return ''

    def _ai_playbook_quote(self, playbook, data, summary):
        """Cotización en borrador con los productos que nombró el cliente,
        para que el equipo la revise y la envíe con un clic."""
        if 'sale.order' not in self.env or not self.partner_id:
            return self._ai_playbook_activity(playbook, summary)
        text = ' '.join(str(value) for value in data.values())
        from .knowledge_search import terms_of
        wanted = terms_of(text)
        Product = self.env['product.product'].sudo()
        candidates = Product.browse()
        for word in list(wanted)[:8]:
            candidates |= Product.search([('sale_ok', '=', True), ('name', 'ilike', word)], limit=5)
        # Solo los que más palabras comparten con lo que pidió el cliente:
        # «escritorios elevables eléctricos» no debe traer «Lámpara de escritorio».
        scored = [(len(wanted & terms_of(product.name, minimum=3)), product) for product in candidates]
        best = max((score for score, _product in scored), default=0)
        products = Product.browse([product.id for score, product in scored if best and score == best])
        quantity = next((int(number) for number in re.findall(r'\b\d{1,4}\b', text) if int(number) > 0), 1)
        try:
            with self.env.cr.savepoint():
                order = self.env['sale.order'].sudo().create({
                    'partner_id': self.partner_id.id,
                    'note': summary,
                    'order_line': [(0, 0, {'product_id': product.id, 'product_uom_qty': quantity})
                                   for product in products[:3]],
                })
        except Exception as exc:  # noqa: BLE001 - sin cotización igual pasa a una persona
            _logger.info('No se creó la cotización del guion en %s: %s', self.id, exc)
            return self._ai_playbook_activity(playbook, summary)
        self.sudo().action_post_internal_note(
            _('Cotización en borrador %(order)s preparada con los datos del guion: revisa productos y precios '
              'antes de enviarla.') % {'order': order.name})
        return order

    def _ai_playbook_activity(self, playbook, summary):
        user = self.assigned_user_id or self.whatsapp_number_id.member_ids[:1] or self.env.user
        try:
            with self.env.cr.savepoint():
                return self.sudo().activity_schedule(
                    'mail.mail_activity_data_todo', user_id=user.id,
                    summary=_('Atender: %s') % playbook.name, note=summary)
        except Exception as exc:  # noqa: BLE001
            _logger.info('No se creó la tarea del guion en %s: %s', self.id, exc)
            return False

    # ------------------------------------------------------------------
    # Seguimiento de guiones a medias
    # ------------------------------------------------------------------
    @api.model
    def _cron_ai_followups(self, limit=50):
        """Un recordatorio amable si el cliente dejó un guion a medias.

        Solo dentro de la ventana de 24 h de WhatsApp (sin plantilla), una vez
        por pausa del cliente y nunca con la IA pausada.
        """
        now = fields.Datetime.now()
        channels = self.sudo().search([
            ('ai_playbook_id', '!=', False), ('ai_playbook_done', '=', False), ('ai_paused', '=', False),
            ('channel_type', '=', 'whatsapp'), ('last_message_date', '>=', now - timedelta(hours=23)),
        ], limit=limit * 4)
        sent = 0
        Message = self.env['chatroom.message']
        for channel in channels:
            profile = channel._ai_agent_profile()
            if not profile or profile.followup_hours <= 0 or sent >= limit:
                continue
            last = Message.search([('channel_id', '=', channel.id)], order='id desc', limit=1)
            last_inbound = Message.search([('channel_id', '=', channel.id), ('direction', '=', 'inbound')],
                                          order='id desc', limit=1)
            if (not last or last.direction != 'outbound' or not last.ai_generated or not last_inbound
                    or last.date > now - timedelta(hours=profile.followup_hours)
                    or last_inbound.date < now - timedelta(hours=23)
                    or (channel.ai_followup_sent_at and channel.ai_followup_sent_at >= last_inbound.date)):
                continue
            data = load_data(channel.ai_playbook_data)
            if not channel.ai_playbook_id._missing(data):
                continue
            text = profile._followup_text(channel.ai_playbook_id, data, channel.partner_id.name)
            try:
                with self.env.cr.savepoint():
                    channel.with_context(chatroom_ai_generated=True).action_send_text(text)
                    channel.ai_followup_sent_at = now
                channel._ai_log_event({'status': 'followup', 'reason': channel.ai_playbook_id.name}, 0, False,
                                      kind='followup')
                sent += 1
            except Exception as exc:  # noqa: BLE001
                _logger.info('No se envió el seguimiento en %s: %s', channel.id, exc)
        return sent

    # ------------------------------------------------------------------
    # Arranque: responder solo lo respaldado desde el primer día
    # ------------------------------------------------------------------
    @api.model
    def _ai_bootstrap_decision(self, draft, intent=False, line=None, company=None, profile=None):
        """(sí/no, motivo) de enviar sola en un tipo aún supervisado."""
        profile = profile if profile is not None else self.env['chatroom.ai.agent.profile']._for_line(
            line, company)
        if not profile or not profile.bootstrap_autonomy:
            return False, ''
        if learning_param(self.env, 'autonomy_frozen', False):
            return False, _('La autonomía está congelada por las pruebas.')
        level = self.env['chatroom.ai.autonomy.level'].sudo()._for(intent or 'otro', line, company)
        if level.state != 'supervised' or level.locked:
            return False, ''
        if draft.get('backing') not in SAFE_BACKINGS:
            return False, _('La respuesta no está respaldada por la información publicada.')
        if draft.get('gap') or (draft.get('needs_human') and draft.get('backing') != 'guion'):
            return False, _('La IA no tenía toda la información.')
        # Pedir un dato del guion o saludar es de bajo riesgo: basta el mínimo de
        # la guardia. Afirmar algo exige la confianza del perfil.
        low_risk = draft.get('backing') in ('guion', 'cortesia')
        threshold = min(profile.bootstrap_min_confidence, self._ai_safety_policy()['min_confidence']) \
            if low_risk else profile.bootstrap_min_confidence
        if draft.get('confidence', 0.0) < threshold:
            return False, _('Confianza %(c).0f%% menor al %(m).0f%% requerido.') % {
                'c': draft.get('confidence', 0.0) * 100, 'm': threshold * 100}
        missing = unsupported_numbers(draft.get('reply'), draft.get('grounding_text'))
        if missing:
            return False, _('Menciona cifras que no están en la información: %s.') % ', '.join(sorted(missing))
        needs_check = not (low_risk and only_asks(draft.get('reply')))
        threshold = profile._verify_threshold()
        if needs_check and threshold is not None and draft.get('backing') == 'conocimiento':
            ratio = self._ai_copied_ratio(draft.get('reply'), draft.get('facts_text') or draft.get('grounding_text'))
            if ratio >= threshold:
                needs_check = False
                draft['copied_ratio'] = ratio
        if profile.verify_before_send and needs_check:
            verified, detail = self._ai_verify_grounding(draft)
            if not verified:
                return False, _('El verificador no encontró respaldo: %s') % (detail or _('sin detalle'))
        return True, _('respaldada por %(backing)s, con %(c).0f%% de confianza.') % {
            'backing': draft['backing'], 'c': draft['confidence'] * 100}

    @api.model
    def _ai_verify_grounding(self, draft):
        """Segunda consulta breve: ¿cada afirmación está escrita en la información?

        El modelo que redacta tiende a declarar respaldo aunque haya deducido
        la respuesta; un verificador aparte, con una sola pregunta, lo detecta.
        El resultado se guarda en el borrador para no repetir la consulta.
        """
        if 'verified' in draft:
            return draft['verified'], draft.get('verify_detail', '')
        try:
            data = self.env['chatroom.ai.service'].complete_json([
                {'role': 'system', 'content': _(
                    'Eres un verificador estricto de respuestas de atención al cliente. Recibes la '
                    'INFORMACIÓN OFICIAL, la pregunta del cliente y una RESPUESTA propuesta. Decide si '
                    'cada afirmación de la respuesta (datos, precios, plazos, condiciones, políticas o un '
                    'sí/no) está escrita explícitamente en la información oficial. Las preguntas al '
                    'cliente, saludos y ofrecimientos de ayuda no son afirmaciones. Si algo se deduce o '
                    'se supone, NO está respaldado. Devuelve SOLO JSON: {"respaldada": true, '
                    '"sin_respaldo": "afirmación no respaldada o vacío"}')},
                {'role': 'user', 'content': _(
                    'INFORMACIÓN OFICIAL:\n%(info)s\n\nPREGUNTA DEL CLIENTE:\n%(question)s\n\n'
                    'RESPUESTA PROPUESTA:\n%(reply)s') % {
                        'info': (draft.get('facts_text') or draft.get('grounding_text') or '')[-8000:],
                        'question': draft.get('question') or '', 'reply': draft.get('reply') or ''}},
            ], required_keys=('respaldada',), task_type='classification', timeout=40)
            verified = data.get('respaldada') is True or str(data.get('respaldada')).strip().lower() in (
                'true', 'si', 'sí', 'yes')
            detail = str(data.get('sin_respaldo') or '').strip()[:250]
        except Exception as exc:  # noqa: BLE001 - sin verificación no se envía sola
            _logger.info('No se pudo verificar la respuesta: %s', exc)
            verified, detail = False, _('no se pudo verificar')
        draft['verified'], draft['verify_detail'] = verified, detail
        return verified, detail

    def _ai_deliver_guarded_reply(self, reply, confidence, intent=False, reason=False):
        draft = self.env.cr.cache.get(DRAFT_CACHE, {}).pop(self.id, None)
        context = self.env.context
        if context.get('chatroom_ai_local_reply') and self._ai_agent_profile():
            # Saludo o agradecimiento del perfil: texto fijo y seguro, se envía
            # sin esperar aprobación (igual que muestra el probador).
            self.env.cr.cache.setdefault(LOCAL_CACHE, set()).add(self.id)
            return super(ChatroomChannel, self.with_context(chatroom_ai_level_auto=True)) \
                ._ai_deliver_guarded_reply(reply, confidence, intent=intent, reason=reason)
        if (draft and draft.get('reply') == reply and not context.get('chatroom_ai_local_reply')
                and not context.get('chatroom_ai_level_auto')):
            allowed, why = self._ai_bootstrap_decision(
                draft, intent or self.ai_intent, self.whatsapp_number_id, self.company_id)
            if draft.get('cached'):
                why = _('%s (respuesta reutilizada, sin consultar a la IA)') % why
            elif allowed:
                self._ai_cache_store(draft)
            if allowed:
                return super(ChatroomChannel, self.with_context(chatroom_ai_level_auto=True)) \
                    ._ai_deliver_guarded_reply(reply, confidence, intent=intent,
                                               reason=_('Arranque con conocimiento: %s') % why)
        return super()._ai_deliver_guarded_reply(reply, confidence, intent=intent, reason=reason)

    def _ai_cache_store(self, draft):
        """Guarda la respuesta para la misma primera pregunta si es general."""
        question = draft.get('cache_question')
        profile = self._ai_agent_profile()
        if not question or not profile or draft.get('backing') != 'conocimiento' or draft.get('playbook_code'):
            return False
        first = (self.partner_id.name or '').strip().split(' ')[0].lower()
        if first and len(first) > 2 and first in (draft.get('reply') or '').lower():
            return False  # personalizada con el nombre: no sirve para otros
        try:
            with self.env.cr.savepoint():
                return self.env['chatroom.ai.reply.cache']._put(profile, question, draft)
        except Exception as exc:  # noqa: BLE001
            _logger.info('No se guardó la respuesta reutilizable: %s', exc)
            return False

    # ------------------------------------------------------------------
    # Respuestas con voz
    # ------------------------------------------------------------------
    def action_send_text(self, body, reply_to_id=False):
        context = self.env.context
        if len(self) == 1 and context.get('chatroom_ai_generated') and not context.get('chatroom_ai_voice_done'):
            profile = self._ai_agent_profile()
            if profile and profile._wants_voice(self):
                try:
                    audio = self._ai_speech(body, profile)
                    if audio:
                        messages = self.with_context(chatroom_ai_voice_done=True).action_send_message(
                            attachments=[{'name': 'respuesta.ogg', 'mimetype': 'audio/ogg',
                                          'data': base64.b64encode(audio).decode()}], reply_to_id=reply_to_id)
                        messages.sudo().write({'ai_transcript': body})
                        return messages
                except Exception as exc:  # noqa: BLE001 - si la voz falla, sale el texto
                    _logger.info('Respuesta con voz no disponible en %s: %s', self.id, exc)
        return super().action_send_text(body, reply_to_id=reply_to_id)

    def _ai_speech(self, text, profile):
        """Nota de voz (ogg/opus, el formato de WhatsApp) con la voz del perfil."""
        provider = self._ai_provider_base()
        if not provider or not (text or '').strip():
            return b''
        base, key = provider
        model = self.env['ir.config_parameter'].sudo().get_param('chatroom_ai.tts_model', 'tts-1')
        response = requests.post(
            '%s/audio/speech' % base, headers={'Authorization': 'Bearer %s' % key}, timeout=60,
            json={'model': model, 'voice': profile.voice_name or 'nova', 'input': text.strip()[:4000],
                  'response_format': 'opus'})
        response.raise_for_status()
        return response.content

    @api.model
    def _ai_predict_decision(self, draft, line=None, company=None, profile=None):
        """Qué haría producción con este borrador, sin enviar nada.

        Refleja la guardia (traspaso por evaluación, sentimiento, confianza,
        calificación comercial), la autonomía por niveles, el arranque con
        conocimiento y la aprobación general.
        :return: (send|approval|review|handoff, motivo)
        """
        company = company or self.env.company
        if learning_param(self.env, 'handoff_enabled', True):
            rule, why = self.env['chatroom.ai.handoff.rule'].sudo()._match_draft(draft, company=company)
            if rule:
                return 'handoff', '%s: %s' % (rule.name, why)
        policy = self._ai_safety_policy()
        reply, confidence, intent = draft.get('reply'), draft.get('confidence', 0.0), draft.get('intent')
        needs_human, reason = draft.get('needs_human'), draft.get('reason') or ''
        if policy['escalate_negative'] and (draft.get('sentiment') == 'negative'
                                            or draft.get('urgency') in ('high', 'critical')):
            needs_human, reason = True, _('Sentimiento negativo o urgencia.')
        if not reply:
            needs_human, reason = True, _('La IA no produjo una respuesta utilizable.')
        if confidence < policy['min_confidence']:
            needs_human = True
            reason = _('Confianza %(c).0f%% menor al mínimo de %(m).0f%%.') % {
                'c': confidence * 100, 'm': policy['min_confidence'] * 100}
        if needs_human and not self._ai_can_auto_qualify(
                reply, intent, draft.get('sentiment'), draft.get('urgency'), confidence):
            return 'review', reason or _('La IA pidió revisión humana.')
        level = self.env['chatroom.ai.autonomy.level'].sudo()._for(intent or 'otro', line, company)
        if level.state == 'blocked' or (level.state == 'automatic' and not level.allows_automatic()):
            return 'review', level.supervision_reason()
        if level.allows_automatic():
            return 'send', _('Nivel automático ganado para «%s».') % level.name
        allowed, why = self._ai_bootstrap_decision(draft, intent, line, company, profile)
        if allowed:
            return 'send', _('Arranque con conocimiento: %s') % why
        if self._ai_requires_approval():
            return 'approval', why or level.supervision_reason()
        return 'send', _('La aprobación general está desactivada.')

    # ------------------------------------------------------------------
    # Respuestas rápidas, aprendizaje y panel
    # ------------------------------------------------------------------
    def _ai_local_reply(self):
        profile = self._ai_agent_profile()
        if not profile:
            return super()._ai_local_reply()
        # Solo si TODO lo que escribió es saludo o agradecimiento: «hola» +
        # «¿cuánto cuesta?» lo responde la IA.
        pending = self._ai_pending_inbound() or self._ai_latest_inbound()
        replies = [profile._local_reply(message._ai_text(), self.partner_id.name) for message in pending]
        return replies[-1] if replies and all(replies) else False

    def _ai_learn_from_human_reply(self, message):
        super()._ai_learn_from_human_reply(message)
        # Respondió una persona: ya no hay borrador pendiente en la lista.
        if self.ai_list_state in ('ai', 'draft'):
            self.sudo().ai_list_state = 'human' if self.ai_paused else False
        self.env['chatroom.ai.knowledge.gap']._capture_answer(self, message)

    def get_ai_assistant_data(self):
        data = super().get_ai_assistant_data()
        playbook, values, done = self._ai_playbook_state()
        data['playbook'] = playbook._progress(values, done) if playbook else False
        if data['playbook']:
            data['playbook']['collected'] = [
                {'label': field.label, 'value': values.get(field.key)}
                for field in playbook.field_ids if values.get(field.key)]
        data['can_take_over'] = bool(self.ai_paused and self.assigned_user_id != self.env.user) or bool(
            data.get('handoff_reason') and self.assigned_user_id != self.env.user)
        return data

    def write(self, vals):
        if 'ai_paused' in vals and not vals['ai_paused'] and 'ai_list_state' not in vals:
            vals = dict(vals, ai_list_state=False)
        return super().write(vals)

    def action_ai_take_over(self):
        """«Tomar conversación»: queda a mi cargo, la IA en pausa y el aviso cerrado."""
        self.ensure_one()
        user = self.env.user
        self.sudo().write({'assigned_user_id': user.id, 'ai_paused': True, 'ai_pause_source': 'human',
                           'ai_list_state': 'human'})
        todo = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        pending = self.sudo().activity_ids.filtered(lambda activity: activity.activity_type_id == todo)
        if pending:
            pending.action_feedback(feedback=_('Tomada por %s.') % user.name)
        if 'chatroom.notification' in self.env:
            notices = self.env['chatroom.notification'].sudo().search([
                ('channel_id', '=', self.id), ('state', 'in', ('unread', 'read'))])
            if notices and 'state' in notices._fields:
                notices.write({'state': 'done'})
        self.sudo().action_post_internal_note(_('%s tomó la conversación.') % user.name)
        return self.get_ai_assistant_data()

    def action_open_in_chat(self):
        self.ensure_one()
        return {'type': 'ir.actions.client', 'tag': 'chatroom_whatsapp.chatroom_app',
                'name': self.display_name, 'params': {'channel_id': self.id}}

    def action_ai_reset_playbook(self):
        self.sudo().write({'ai_playbook_id': False, 'ai_playbook_data': False, 'ai_playbook_done': False})
        return self.get_ai_assistant_data() if len(self) == 1 else True

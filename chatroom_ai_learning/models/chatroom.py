# -*- coding: utf-8 -*-
import logging
from datetime import timedelta

from odoo import _, api, fields, models, modules

from .autonomy_level import learning_param
from .learning_utils import text_similarity

_logger = logging.getLogger(__name__)


class ChatroomChannel(models.Model):
    _inherit = 'chatroom.channel'

    ai_pause_source = fields.Selection([
        ('human', 'Una persona tomó la conversación'),
        ('handoff', 'Traspaso automático a una persona'),
        ('unsafe', 'Respuesta marcada como no segura'),
    ], string='Motivo de la pausa de IA', copy=False)
    ai_memory_extracted_at = fields.Datetime(string='Memoria actualizada el', copy=False)

    # ------------------------------------------------------------------
    # Contexto: ejemplos aprobados por el equipo
    # ------------------------------------------------------------------
    def _ai_build_conversation(self, extra_system=None):
        conversation = super()._ai_build_conversation(extra_system=extra_system)
        sources = self._ai_sources() if hasattr(self, '_ai_sources') else {}
        if not conversation or not sources.get('examples', True):
            return conversation
        query = next((turn['content'] for turn in reversed(conversation) if turn['role'] == 'user'), '')
        examples = self.env['chatroom.ai.example'].sudo()._find(
            query, category=self.ai_intent or False, line=self.whatsapp_number_id,
            company=self.company_id, exclude_inbound=self.env.context.get('chatroom_ai_history_until'))
        if examples:
            conversation[0]['content'] += '\n\n' + examples._prompt_block()
        return conversation

    @api.model
    def _ai_offline_system(self, turns, category=False, line=None, company=None, partner=None):
        """Instrucciones para una conversación sin canal real (casos de
        prueba, probador del agente). Las extensiones agregan aquí lo mismo
        que agregan en producción: lo que se prueba es lo que se responde."""
        query = next((turn['content'] for turn in reversed(turns) if turn['role'] == 'user'), '')
        system = self._ai_guarded_draft_prompt()
        examples = self.env['chatroom.ai.example'].sudo()._find(
            query, category=category, line=line, company=company or self.env.company)
        if examples:
            system += '\n\n' + examples._prompt_block()
        return system

    # ------------------------------------------------------------------
    # Traspaso a una persona
    # ------------------------------------------------------------------
    def _ai_latest_inbound(self):
        self.ensure_one()
        return self.env['chatroom.message'].search([
            ('channel_id', '=', self.id), ('direction', '=', 'inbound')], order='date desc, id desc', limit=1)

    def action_ai_auto_reply_safe(self):
        self.ensure_one()
        if (not self.ai_paused and learning_param(self.env, 'handoff_enabled', True)
                and self._ai_safety_policy()['enabled']):
            # Toda la ráfaga del cliente, no solo el último mensaje: «me
            # cobraron dos veces» seguido de «hola?» igual pasa a una persona.
            pending = self._ai_pending_inbound() or self._ai_latest_inbound()
            rule, reason = self.env['chatroom.ai.handoff.rule'].sudo()._match_text(
                '\n'.join(message._ai_text() for message in pending), company=self.company_id)
            if rule:
                return self._ai_handoff(rule, reason)
        return super().action_ai_auto_reply_safe()

    def _ai_after_guarded_draft(self, draft):
        handled = super()._ai_after_guarded_draft(draft)
        if handled or not learning_param(self.env, 'handoff_enabled', True):
            return handled
        rule, reason = self.env['chatroom.ai.handoff.rule'].sudo()._match_draft(draft, company=self.company_id)
        if rule:
            return self._ai_handoff(rule, reason, draft=draft)
        return False

    def _ai_handoff_summary(self):
        """Resumen para que el equipo no vuelva a preguntar lo mismo."""
        self.ensure_one()
        messages = self.message_ids.filtered(lambda message: message.body).sorted('date')[-6:]
        customer, advisor = _('Cliente'), _('Asesor')
        excerpt = '\n'.join('%s: %s' % (customer if message.direction == 'inbound' else advisor,
                                        message.body[:300]) for message in messages)
        try:
            summary = self._ai_chat_completion(self._ai_build_conversation(extra_system=_(
                'Resume en máximo 4 líneas, para la persona que tomará esta conversación: qué '
                'quiere el cliente, qué se le respondió y qué falta resolver. En español.')),
                task_type='summary')
            return (summary or '').strip() or excerpt
        except Exception as exc:  # noqa: BLE001 - sin IA se deja el extracto
            _logger.info('Resumen de traspaso sin IA en %s: %s', self.id, exc)
            return excerpt

    def _ai_handoff_users(self, rule):
        self.ensure_one()
        if rule.notify == 'line' and self.whatsapp_number_id.member_ids:
            return self.whatsapp_number_id.member_ids
        if rule.notify == 'managers':
            group = self.env.ref('chatroom_whatsapp.group_chatroom_manager', raise_if_not_found=False)
            return group.user_ids if group else self.env['res.users']
        return self.assigned_user_id or self.whatsapp_number_id.member_ids[:1] or self.env.user

    def _ai_handoff(self, rule, reason, draft=None):
        """Pasa la conversación a una persona: pausa, avisa y deja resumen."""
        self.ensure_one()
        rule._register_match()
        values = {'ai_handoff_reason': ('%s: %s' % (rule.name, reason))[:250]}
        if rule.pause_ai:
            values.update(ai_paused=True, ai_pause_source='handoff')
        if 'ai_flow_state' in self._fields:
            values['ai_flow_state'] = 'human'
        self.sudo().write(values)
        note = _('Traspaso a una persona — %(rule)s. %(reason)s') % {'rule': rule.name, 'reason': reason}
        if rule.post_summary:
            note += '\n' + _('Resumen: %s') % self._ai_handoff_summary()
        self.sudo().action_post_internal_note(note)
        for user in self._ai_handoff_users(rule):
            self._ai_handoff_notify(user, rule, reason)
        if rule.customer_message:
            try:
                self.with_context(chatroom_ai_generated=True).action_send_text(rule.customer_message)
            except Exception as exc:  # noqa: BLE001 - fuera de ventana de 24 h, sin credenciales...
                _logger.info('No se envió el aviso de traspaso en %s: %s', self.id, exc)
        return {'status': 'handoff', 'rule': rule.name, 'reason': reason}

    def _ai_handoff_notify(self, user, rule, reason):
        if 'chatroom.notification' in self.env:
            self.env['chatroom.notification'].sudo().create_deduplicated({
                'name': _('Conversación para ti: %s') % self.display_name,
                'message': '%s — %s' % (rule.name, reason),
                'notification_type': 'ai',
                'priority': '2',
                'user_id': user.id,
                'channel_id': self.id,
                'partner_id': self.partner_id.id,
                'res_model': 'chatroom.channel',
                'res_id': self.id,
                'dedupe_key': 'ai-handoff:%s:%s' % (self.id, user.id),
                'escalation_level': 1,
            })
        else:
            self.sudo().activity_schedule(
                'mail.mail_activity_data_todo', user_id=user.id,
                summary=_('Atender conversación: %s') % rule.name, note=reason)

    # ------------------------------------------------------------------
    # Autonomía por niveles
    # ------------------------------------------------------------------
    def _ai_deliver_guarded_reply(self, reply, confidence, intent=False, reason=False):
        if (self.env.context.get('chatroom_ai_local_reply') or self.env.context.get('chatroom_ai_level_auto')
                or not learning_param(self.env, 'graduated_autonomy', True)):
            return super()._ai_deliver_guarded_reply(reply, confidence, intent=intent, reason=reason)
        level = self.env['chatroom.ai.autonomy.level'].sudo()._for(
            intent or self.ai_intent or 'otro', self.whatsapp_number_id, self.company_id)
        if level.state == 'blocked' or (level.state == 'automatic' and not level.allows_automatic()):
            why = level.supervision_reason()
            suggestion = self._ai_create_guarded_suggestion(reply, confidence, 'human_review', why, intent=intent)
            return {'status': 'human_review', 'suggestion_id': suggestion.id, 'reason': why}
        if level.allows_automatic():
            # El nivel ganado es la aprobación de este tipo de conversación:
            # responde sola aunque la aprobación general esté activa.
            return super(ChatroomChannel, self.with_context(chatroom_ai_level_auto=True))._ai_deliver_guarded_reply(
                reply, confidence, intent=intent,
                reason=_('%s Nivel automático ganado para «%s».') % (reason or '', level.name))
        return super()._ai_deliver_guarded_reply(reply, confidence, intent=intent, reason=reason)

    def _ai_requires_approval(self):
        if self.env.context.get('chatroom_ai_level_auto'):
            return False
        return super()._ai_requires_approval()

    def get_ai_assistant_data(self):
        data = super().get_ai_assistant_data()
        level = self.env['chatroom.ai.autonomy.level'].sudo()._for(
            self.ai_intent or 'otro', self.whatsapp_number_id, self.company_id)
        data['autonomy_level'] = {
            'category': level.name, 'state': level.state,
            'state_label': dict(level._fields['state'].selection)[level.state],
            'automatic': level.allows_automatic(), 'note': level.status_note or '',
        }
        data['handoff_reason'] = self.ai_handoff_reason or '' if self.ai_paused else ''
        return data

    # ------------------------------------------------------------------
    # Aprender de lo que responde una persona
    # ------------------------------------------------------------------
    def _ai_learn_from_human_reply(self, message):
        """Una persona respondió: se compara con el borrador de la IA si lo
        había o, en modo sombra, se encola que la IA redacte a ciegas."""
        self.ensure_one()
        inbound = self.env['chatroom.message'].search([
            ('channel_id', '=', self.id), ('direction', '=', 'inbound'), ('id', '<', message.id),
        ], order='id desc', limit=1)
        if not inbound or not inbound.body:
            return
        previous_outbound = self.env['chatroom.message'].search_count([
            ('channel_id', '=', self.id), ('direction', '=', 'outbound'),
            ('id', '>', inbound.id), ('id', '<', message.id)])
        if previous_outbound:
            return  # Solo la primera respuesta a cada mensaje del cliente.
        Evaluation = self.env['chatroom.ai.evaluation'].sudo()
        if Evaluation.search_count([('inbound_message_id', '=', inbound.id)]):
            return
        base = {'channel_id': self.id, 'company_id': self.company_id.id,
                'line_id': self.whatsapp_number_id.id or False, 'customer_message': inbound.body,
                'human_text': message.body, 'inbound_message_id': inbound.id,
                'human_message_id': message.id, 'category': self.ai_intent or False}
        suggestion = self.env['chatroom.ai.suggestion'].sudo().search([
            ('channel_id', '=', self.id), ('state', 'in', ('draft', 'approved')),
            ('create_date', '>=', fields.Datetime.now() - timedelta(hours=12)),
        ], order='create_date desc, id desc', limit=1)
        if suggestion:
            score = text_similarity(suggestion.suggested_text, message.body)
            verdict = 'good' if score >= 0.9 else 'acceptable' if score >= 0.6 else 'bad'
            Evaluation.create(dict(base, source='suggestion', ai_text=suggestion.suggested_text,
                                   suggestion_id=suggestion.id, verdict=verdict, score=score,
                                   category=suggestion.intent or base['category'],
                                   reason=_('Comparado con lo que envió la persona.')))
            if suggestion.feedback_state == 'pending':
                suggestion.write({'feedback_state': {'good': 'helpful', 'acceptable': 'edited'}.get(
                    verdict, 'edited'), 'state': 'sent'})
            return
        if not self._ai_shadow_should_sample(inbound):
            return
        Evaluation.create(dict(base, source='shadow', state='pending'))
        cron = self.env.ref('chatroom_ai_learning.ir_cron_shadow', raise_if_not_found=False)
        if cron:
            cron._trigger()

    def _ai_shadow_should_sample(self, inbound):
        if not learning_param(self.env, 'shadow_enabled', True) or not self._ai_get_credentials():
            return False
        rate = learning_param(self.env, 'shadow_rate', 50)
        if (inbound.id * 2654435761) % 100 >= rate:
            return False
        start = fields.Datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today = self.env['chatroom.ai.evaluation'].sudo().search_count([
            ('source', '=', 'shadow'), ('create_date', '>=', start)])
        return today < learning_param(self.env, 'shadow_daily_limit', 200)

    # ------------------------------------------------------------------
    # Reactivación automática y memoria
    # ------------------------------------------------------------------
    def write(self, vals):
        # Una persona que toma la conversación pausa la IA (chatroom_whatsapp):
        # se registra el motivo para poder reactivarla después.
        if vals.get('ai_paused') and 'ai_pause_source' not in vals:
            vals = dict(vals, ai_pause_source='human')
        if 'ai_paused' in vals and not vals['ai_paused']:
            vals = dict(vals, ai_pause_source=False)
        return super().write(vals)

    @api.model
    def _cron_resume_ai(self):
        """Devuelve la conversación a la IA cuando la persona ya respondió y
        pasaron N horas sin actividad. Nunca tras una respuesta insegura."""
        hours = learning_param(self.env, 'resume_after_hours', 12)
        if hours <= 0:
            return 0
        cutoff = fields.Datetime.now() - timedelta(hours=hours)
        channels = self.search([('ai_paused', '=', True), ('ai_pause_source', 'in', ('human', 'handoff')),
                                ('last_message_date', '<', cutoff)], limit=200)
        resumed = self.browse()
        for channel in channels:
            last = self.env['chatroom.message'].search([('channel_id', '=', channel.id)],
                                                       order='date desc, id desc', limit=1)
            if last.direction == 'outbound':  # El cliente no quedó esperando.
                resumed |= channel
        if resumed:
            resumed.write({'ai_paused': False})
            for channel in resumed:
                channel.message_post(body=_('IA reactivada: la persona ya respondió y pasaron %s h '
                                            'sin actividad.') % hours, subtype_xmlid='mail.mt_note')
        return len(resumed)

    def _ai_memory_consent_ok(self):
        self.ensure_one()
        if not self.partner_id:
            return False
        if 'ec.data.consent' not in self.env:
            return True
        codes = [code.strip() for code in learning_param(
            self.env, 'memory_consent_codes', 'TRATAMIENTO,ASESORIA_IA').split(',') if code.strip()]
        consent = self.env['ec.data.consent'].sudo()
        partners = self.partner_id | self.partner_id.commercial_partner_id
        return any(consent.has_active_consent(partner.id, code) for partner in partners for code in codes)

    @api.model
    def _cron_extract_memories(self, limit=20):
        if not learning_param(self.env, 'memory_enabled', True) or 'chatroom.ai.memory' not in self.env:
            return 0
        # Conversaciones quietas hace 30 min con actividad de la última semana;
        # se saltan las que no tuvieron mensajes desde la última extracción.
        now = fields.Datetime.now()
        channels = self.search([
            ('partner_id', '!=', False), ('last_message_date', '<', now - timedelta(minutes=30)),
            ('last_message_date', '>=', now - timedelta(days=7)),
        ], order='last_message_date desc', limit=limit * 5)
        done = 0
        auto_commit = not modules.module.current_test
        for channel in channels:
            if channel.ai_memory_extracted_at and channel.ai_memory_extracted_at >= channel.last_message_date:
                continue
            if done >= limit:
                break
            try:
                with self.env.cr.savepoint():
                    channel._ai_extract_memories()
                done += 1
            except Exception as exc:  # noqa: BLE001
                _logger.info('Memoria no extraída en %s: %s', channel.id, exc)
            channel.ai_memory_extracted_at = fields.Datetime.now()
            if auto_commit:
                self.env.cr.commit()
        return done

    def _ai_extract_memories(self):
        """Propone datos estables del cliente a partir de la conversación."""
        self.ensure_one()
        if not self._ai_memory_consent_ok():
            return 0
        Memory = self.env['chatroom.ai.memory'].sudo()
        existing = Memory.with_context(active_test=False).search([('partner_id', '=', self.partner_id.id)])
        since = self.ai_memory_extracted_at
        messages = self.message_ids.filtered(lambda message: message.body and (
            not since or message.date > since)).sorted('date')[-40:]
        if not messages.filtered(lambda message: message.direction == 'inbound'):
            return 0
        customer, advisor = _('Cliente'), _('Asesor')
        transcript = '\n'.join('%s: %s' % (customer if message.direction == 'inbound' else advisor,
                                           message.body) for message in messages)
        known = '\n'.join('- %s: %s' % (memory.name, memory.content) for memory in existing[:30])
        data = self.env['chatroom.ai.service'].complete_json([
            {'role': 'system', 'content': _(
                'Extraes de una conversación datos ESTABLES y útiles del cliente para atenderlo mejor '
                'la próxima vez: preferencias, datos de su negocio o vehículo, compromisos acordados. '
                'Nada de datos sensibles (salud, religión, política, contraseñas, números de tarjeta). '
                'No repitas lo ya sabido. Devuelve ÚNICAMENTE JSON: {"hechos": [{"titulo": "corto", '
                '"contenido": "una frase", "tipo": "fact|preference|commitment|outcome", '
                '"confianza": 0.0-1.0}]}')},
            {'role': 'user', 'content': _('Ya sabido:\n%(known)s\n\nConversación:\n%(transcript)s') % {
                'known': known or _('(nada)'), 'transcript': transcript}},
        ], required_keys=('hechos',), task_type='summary', timeout=60)
        created = 0
        valid_types = dict(Memory._fields['memory_type'].selection)
        for item in (data.get('hechos') or [])[:8]:
            if not isinstance(item, dict) or not str(item.get('contenido') or '').strip():
                continue
            try:
                confidence = max(0.0, min(1.0, float(item.get('confianza'))))
            except (TypeError, ValueError):
                confidence = 0.5
            title = str(item.get('titulo') or item.get('contenido'))[:80]
            content = str(item['contenido']).strip()[:500]
            same = existing.filtered(lambda memory: text_similarity(memory.content, content) >= 0.85)
            if same:
                continue
            approved = confidence >= learning_param(self.env, 'memory_min_confidence', 0.8)
            Memory.create({
                'name': title, 'content': content, 'partner_id': self.partner_id.id,
                'channel_id': self.id, 'memory_type': item.get('tipo') if item.get('tipo') in valid_types else 'fact',
                'source': 'conversation', 'confidence': confidence, 'active': approved,
                'review_state': 'approved' if approved else 'pending',
                'source_ref': 'chatroom.channel,%s' % self.id, 'company_id': self.company_id.id,
            })
            created += 1
        return created


class ChatroomMessage(models.Model):
    _inherit = 'chatroom.message'

    @api.model_create_multi
    def create(self, vals_list):
        messages = super().create(vals_list)
        for message in messages:
            if (message.direction == 'outbound' and message.body and message.sender_user_id
                    and not message.sender_user_id._is_superuser() and not message.ai_generated and message.message_type == 'text'
                    and message.channel_id.channel_type == 'whatsapp'):
                try:
                    with self.env.cr.savepoint():
                        message.channel_id._ai_learn_from_human_reply(message)
                except Exception as exc:  # noqa: BLE001 - aprender nunca debe frenar el envío
                    _logger.info('No se registró el aprendizaje del mensaje %s: %s', message.id, exc)
        return messages


class ChatroomAiSuggestion(models.Model):
    _inherit = 'chatroom.ai.suggestion'

    def _set_feedback(self, state):
        result = super()._set_feedback(state)
        Evaluation = self.env['chatroom.ai.evaluation'].sudo()
        verdict = {'helpful': 'good', 'edited': 'acceptable', 'unsafe': 'unsafe'}.get(state)
        for suggestion in (self if verdict else self.browse()):
            channel = suggestion.channel_id
            if state == 'unsafe':
                channel.sudo().write({'ai_pause_source': 'unsafe'})
            Evaluation.create({
                'channel_id': channel.id, 'company_id': channel.company_id.id,
                'line_id': channel.whatsapp_number_id.id or False, 'source': 'feedback',
                'category': suggestion.intent or channel.ai_intent or 'otro', 'verdict': verdict,
                'ai_text': suggestion.suggested_text, 'suggestion_id': suggestion.id,
                'reason': _('Valoración de %s.') % self.env.user.name,
            })
        return result


class ChatroomAiMemory(models.Model):
    _inherit = 'chatroom.ai.memory'

    review_state = fields.Selection([
        ('approved', 'Aprobada'), ('pending', 'Por revisar'), ('rejected', 'Descartada'),
    ], string='Revisión', default='approved', index=True)

    def action_approve_memory(self):
        self.write({'review_state': 'approved', 'active': True})
        return True

    def action_reject_memory(self):
        self.write({'review_state': 'rejected', 'active': False})
        return True

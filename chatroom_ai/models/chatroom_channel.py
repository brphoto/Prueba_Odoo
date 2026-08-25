# -*- coding: utf-8 -*-
import json
import re

from odoo import _, fields, models
from odoo.exceptions import UserError


class ChatroomChannel(models.Model):
    _inherit = 'chatroom.channel'

    def _ai_build_conversation(self, extra_system=None):
        conversation = super()._ai_build_conversation(extra_system=extra_system)
        self.ensure_one()
        context = []
        if 'chatroom.ai.memory' in self.env and self.partner_id:
            memory = self.env['chatroom.ai.memory'].sudo().get_context(
                partner=self.partner_id, channel=self, limit=8)
            if memory:
                context.append('Memoria empresarial autorizada:\n%s' % memory)
        if 'ai.knowledge.base' in self.env:
            query = ' '.join(
                (message.body or '')
                for message in self.message_ids.sorted('date')[-self._ai_history_limit():]
                if message.body
            )
            knowledge = self.env['ai.knowledge.base'].get_sales_context(self, query=query)
            if knowledge:
                context.append('Manuales internos autorizados:\n%s' % knowledge)
        if context and conversation:
            conversation[0]['content'] = '%s\n\n%s' % (conversation[0]['content'], '\n\n'.join(context))
        return conversation

    def get_ai_assistant_data(self):
        """Estado seguro que consume el panel lateral del agente.

        Nunca devuelve el token ni la URL privada del proveedor; solo indica
        si hay configuración suficiente y qué borrador auditable está activo.
        """
        self.ensure_one()
        suggestion = self.env['chatroom.ai.suggestion'].search([
            ('channel_id', '=', self.id), ('state', 'in', ('draft', 'approved')),
        ], order='create_date desc, id desc', limit=1)
        knowledge_count = 0
        if 'ai.knowledge.base' in self.env:
            knowledge_count = self.env['ai.knowledge.base'].sudo().search_count([
                ('active', '=', True), ('state', '=', 'indexed'),
            ])
        usage = self.get_ai_usage_summary() if hasattr(self, 'get_ai_usage_summary') else {
            'requests': 0, 'tokens': 0, 'last_model': '',
        }
        return {
            'provider_ready': bool(self._ai_get_credentials()),
            'approval_required': self._ai_requires_approval(),
            'summary': self.ai_summary or '',
            'intent': self.ai_intent or '',
            'knowledge_count': knowledge_count,
            'usage': usage,
            'safety_policy': self._ai_safety_policy(),
            'ai_paused': self.ai_paused,
            'suggestion': {
                'id': suggestion.id,
                'text': suggestion.suggested_text,
                'state': suggestion.state,
                'intent': suggestion.intent or '',
                'confidence': suggestion.confidence,
                'safety_decision': suggestion.safety_decision,
                'safety_reason': suggestion.safety_reason or '',
                'feedback_state': suggestion.feedback_state,
            } if suggestion else False,
        }

    def _ai_safety_policy(self):
        """Devuelve controles operativos, nunca credenciales."""
        self.ensure_one()
        icp = self.env['ir.config_parameter'].sudo()

        def integer(key, default):
            try:
                return max(0, int(icp.get_param(key, default)))
            except (TypeError, ValueError):
                return default

        try:
            confidence = float(icp.get_param(
                'chatroom_ai_agent.auto_reply_min_confidence', '0.80'))
        except (TypeError, ValueError):
            confidence = 0.80
        return {
            'enabled': self._ai_param_enabled('chatroom_ai_agent.safe_auto_reply', default=True),
            'min_confidence': min(max(confidence, 0.0), 1.0),
            'cooldown_minutes': integer('chatroom_ai_agent.auto_reply_cooldown_minutes', 15),
            'daily_limit': integer('chatroom_ai_agent.auto_reply_daily_limit', 30),
            'escalate_negative': self._ai_param_enabled(
                'chatroom_ai_agent.auto_reply_escalate_negative', default=True),
            'allow_outside_hours': self._ai_param_enabled(
                'chatroom_ai_agent.auto_reply_allow_outside_hours', default=False),
        }

    def _ai_guard_notification(self, reason, priority='1'):
        """Avisa al responsable sin hacer obligatorio el modulo de alertas."""
        self.ensure_one()
        if 'chatroom.notification' not in self.env:
            return False
        user = self.assigned_user_id or self.env.user
        key = 'ai-guard:%s:%s' % (self.id, re.sub(r'\W+', '-', reason.lower())[:50])
        return self.env['chatroom.notification'].sudo().create_deduplicated({
            'name': _('Revision humana requerida por IA'),
            'message': _('%s: %s') % (self.display_name, reason),
            'notification_type': 'ai',
            'priority': priority,
            'user_id': user.id,
            'channel_id': self.id,
            'partner_id': self.partner_id.id,
            'res_model': 'chatroom.channel',
            'res_id': self.id,
            'dedupe_key': key,
            'escalation_level': 2 if priority == '2' else 1,
        })

    def _ai_create_guarded_suggestion(self, reply, confidence, decision, reason, intent=False):
        suggestion = self.env['chatroom.ai.suggestion'].create_from_channel(self, reply)
        suggestion.write({
            'confidence': confidence,
            'intent': intent or self.ai_intent or False,
            'safety_decision': decision,
            'safety_reason': reason,
            'rejection_reason': reason if decision in ('blocked', 'human_review') else False,
        })
        self.ai_suggested_reply = reply
        if decision in ('blocked', 'human_review'):
            self._ai_guard_notification(reason, priority='2' if 'urgencia' in reason.lower() else '1')
        return suggestion

    def _ai_local_reply(self):
        """Respuestas deterministas para casos simples y de bajo riesgo.

        Se ejecuta antes del proveedor externo. No usa tokens ni se activa
        para preguntas mezcladas con otros temas; en esos casos continúa el
        flujo normal de IA con sus controles de confianza.
        """
        self.ensure_one()
        inbound = self.env['chatroom.message'].search([
            ('channel_id', '=', self.id), ('direction', '=', 'inbound'),
        ], order='date desc, id desc', limit=1)
        text = re.sub(r'\s+', ' ', (inbound.body or '').strip().lower())
        text = re.sub(r'[^\wáéíóúñü ]', '', text)
        if not text:
            return False
        if re.fullmatch(r'(hola|buenas|buenos días|buenas tardes|buenas noches|hello|hi)', text):
            name = self.partner_id.name.split(' ')[0] if self.partner_id and self.partner_id.name else ''
            greeting = _('Hola') + (', %s' % name if name else '') + _('. ¿En qué podemos ayudarte?')
            return greeting
        if re.fullmatch(r'(gracias|muchas gracias|gracias por la atención|ok gracias)', text):
            return _('Con gusto. Quedamos atentos para ayudarte.')
        return False

    def _ai_deliver_guarded_reply(self, reply, confidence, intent=False, reason=False):
        """Registra, aprueba y envía una respuesta ya validada."""
        self.ensure_one()
        suggestion = self._ai_create_guarded_suggestion(
            reply, confidence, 'allowed',
            reason or _('Respuesta aprobada por la guardia automatica.'),
            intent=intent)
        if self._ai_requires_approval():
            return {'status': 'awaiting_approval', 'suggestion_id': suggestion.id}
        try:
            self.with_context(chatroom_ai_generated=True).action_send_text(reply)
        except Exception as exc:
            suggestion.write({'state': 'error', 'error_message': str(exc)})
            raise
        suggestion.write({
            'state': 'sent', 'sent_by': self.env.user.id,
            'sent_at': fields.Datetime.now(),
        })
        self.ai_suggested_reply = False
        return {'status': 'sent', 'suggestion_id': suggestion.id}

    def action_ai_auto_reply_safe(self):
        """Genera o envia una respuesta pasando por una politica segura.

        El proveedor debe devolver JSON con respuesta, confianza y si hace
        falta una persona. Un formato inesperado siempre termina en revision;
        nunca se envia texto que no haya pasado la validacion.
        """
        self.ensure_one()
        policy = self._ai_safety_policy()
        if not policy['enabled']:
            return {'status': 'disabled'}
        if self.ai_paused:
            return {'status': 'human_active', 'reason': _('La IA esta pausada porque atiende un agente.')}
        if self.partner_id and getattr(self.partner_id, 'whatsapp_opt_out', False):
            return {'status': 'opted_out', 'reason': _('El contacto desactivo los mensajes.')}
        if not policy['allow_outside_hours'] and hasattr(self, '_is_within_business_hours') \
                and not self._is_within_business_hours():
            reason = _('Fuera del horario de atencion; se requiere revision humana.')
            self._ai_guard_notification(reason)
            return {'status': 'human_review', 'reason': reason}

        message_model = self.env['chatroom.message']
        # Idempotencia: si ya se respondió al último mensaje entrante, no
        # volvemos a llamar al proveedor ni duplicamos el mensaje.
        latest_inbound = message_model.search([
            ('channel_id', '=', self.id), ('direction', '=', 'inbound'),
        ], order='date desc, id desc', limit=1)
        latest_ai = message_model.search([
            ('channel_id', '=', self.id), ('direction', '=', 'outbound'),
            ('ai_generated', '=', True),
        ], order='date desc, id desc', limit=1) if 'ai_generated' in message_model._fields else False
        already_answered = bool(
            latest_inbound and latest_ai and (
                latest_ai.date > latest_inbound.date
                or (latest_ai.date == latest_inbound.date and latest_ai.id > latest_inbound.id)
            )
        )
        if already_answered:
            return {'status': 'already_replied', 'reason': _('El último mensaje entrante ya tiene respuesta automática.')}

        # Saludos y agradecimientos no necesitan consumir tokens.
        local_reply = self._ai_local_reply()
        if local_reply:
            return self._ai_deliver_guarded_reply(
                local_reply, 1.0, intent='consulta',
                reason=_('Respuesta local para una interacción sencilla; no consumió tokens.'))

        now = fields.Datetime.now()
        if 'ai_generated' in message_model._fields:
            latest = message_model.search([
                ('channel_id', '=', self.id), ('direction', '=', 'outbound'),
                ('ai_generated', '=', True),
            ], order='date desc, id desc', limit=1)
            if latest and policy['cooldown_minutes']:
                elapsed = (now - latest.date).total_seconds() / 60.0
                if elapsed < policy['cooldown_minutes']:
                    remaining = max(1, int(policy['cooldown_minutes'] - elapsed))
                    reason = _('Pausa preventiva: espera %s minuto(s) antes de otra respuesta IA.') % remaining
                    self._ai_guard_notification(reason)
                    return {'status': 'cooldown', 'reason': reason}
            if policy['daily_limit']:
                start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                daily_count = message_model.search_count([
                    ('channel_id', '=', self.id), ('direction', '=', 'outbound'),
                    ('ai_generated', '=', True),
                    ('date', '>=', fields.Datetime.to_string(start)),
                ])
                if daily_count >= policy['daily_limit']:
                    reason = _('Se alcanzo el limite diario de respuestas automaticas (%s).') % policy['daily_limit']
                    self._ai_guard_notification(reason, priority='2')
                    return {'status': 'daily_limit', 'reason': reason}

        system_prompt = _(
            'Responde SOLO JSON valido con esta estructura: '
            '{"reply":"texto breve", "confidence":0.0, '
            '"needs_human":false, "reason":"motivo", '
            '"sentiment":"positive|neutral|negative", '
            '"urgency":"low|normal|high|critical", '
            '"intent":"consulta|venta|soporte|queja|otro"}. '
            'No inventes precios, fechas, stock, estados de pago ni promesas. '
            'Marca needs_human=true ante quejas, reclamos, pagos, urgencias, '
            'datos faltantes o cualquier duda. La respuesta debe ser breve, '
            'profesional y en espanol.')
        raw = self._ai_chat_completion(
            self._ai_build_conversation(extra_system=system_prompt), task_type='reply')
        match = re.search(r'\{.*\}', raw or '', re.DOTALL)
        try:
            data = json.loads(match.group(0) if match else raw)
        except (ValueError, TypeError, AttributeError):
            reason = _('El proveedor devolvio un formato no valido; se necesita revision humana.')
            self._ai_guard_notification(reason, priority='2')
            return {'status': 'invalid_provider_response', 'reason': reason}

        reply = (data.get('reply') or '').strip() if isinstance(data, dict) else ''
        try:
            confidence = min(max(float(data.get('confidence', 0.0)), 0.0), 1.0)
        except (TypeError, ValueError, AttributeError):
            confidence = 0.0
        valid_intents = dict(self._fields['ai_intent'].selection)
        intent = data.get('intent') if data.get('intent') in valid_intents else False
        sentiment = data.get('sentiment') or 'neutral'
        urgency = data.get('urgency') or 'normal'
        needs_human = bool(data.get('needs_human'))
        reason = (data.get('reason') or _('La IA solicito revision humana.')).strip()
        if policy['escalate_negative'] and (sentiment == 'negative' or urgency in ('high', 'critical')):
            needs_human = True
            reason = _('Sentimiento negativo o urgencia detectada: %s') % reason
        if not reply:
            needs_human = True
            reason = _('La IA no produjo una respuesta utilizable.')
        if confidence < policy['min_confidence']:
            needs_human = True
            reason = _('Confianza %.0f%% inferior al minimo configurado de %.0f%%.') % (
                confidence * 100, policy['min_confidence'] * 100)

        if needs_human:
            suggestion = self._ai_create_guarded_suggestion(
                reply or _('La IA no genero texto; revisar la conversacion.'),
                confidence, 'human_review', reason, intent=intent)
            return {'status': 'human_review', 'suggestion_id': suggestion.id, 'reason': reason}

        return self._ai_deliver_guarded_reply(
            reply, confidence, intent=intent,
            reason=_('Respuesta aprobada por la guardia automatica.'))

    def action_ai_prepare_suggestion(self, model_id=None):
        self.ensure_one()
        text = self._ai_chat_completion(
            self._ai_build_conversation(), task_type='reply', model_id=model_id)
        suggestion = self.env['chatroom.ai.suggestion'].create_from_channel(self, text)
        return {
            'id': suggestion.id, 'text': suggestion.suggested_text,
            'state': suggestion.state, 'intent': suggestion.intent or '',
            'confidence': suggestion.confidence,
        }

    def action_ai_prepare_summary(self, model_id=None):
        self.ensure_one()
        system_prompt = _(
            'Resume esta conversación de WhatsApp para un agente humano. '
            'Responde en español, en un párrafo corto de máximo 5 líneas, '
            'mencionando qué quiere el cliente y en qué quedó la conversación.')
        self.ai_summary = self._ai_chat_completion(
            self._ai_build_conversation(extra_system=system_prompt),
            task_type='summary', model_id=model_id)
        return self.ai_summary or ''

    def action_ai_classify_intent(self, model_id=None):
        self.ensure_one()
        self.ai_intent = self._ai_classify_intent(model_id=model_id)
        return self.ai_intent

    def _get_ai_suggestion_for_action(self, suggestion_id):
        self.ensure_one()
        suggestion = self.env['chatroom.ai.suggestion'].browse(int(suggestion_id)).exists()
        if not suggestion or suggestion.channel_id != self:
            raise UserError(_('La sugerencia no pertenece a esta conversación.'))
        return suggestion

    def action_ai_approve_suggestion(self, suggestion_id):
        self._get_ai_suggestion_for_action(suggestion_id).action_approve()
        return self.get_ai_assistant_data()

    def action_ai_update_suggestion(self, suggestion_id, text):
        suggestion = self._get_ai_suggestion_for_action(suggestion_id)
        if suggestion.state != 'draft':
            raise UserError(_('Solo se puede editar una sugerencia en borrador.'))
        if not (text or '').strip():
            raise UserError(_('La respuesta no puede quedar vacía.'))
        normalized = text.strip()
        suggestion.write({
            'suggested_text': normalized,
            'edited_by_human': normalized != (suggestion.suggested_text or '').strip(),
            'edit_count': suggestion.edit_count + 1,
            'last_reviewed_at': fields.Datetime.now(),
        })
        return self.get_ai_assistant_data()

    def action_ai_discard_suggestion(self, suggestion_id):
        self._get_ai_suggestion_for_action(suggestion_id).action_reject()
        return self.get_ai_assistant_data()

    def action_ai_send_suggestion(self, suggestion_id):
        self._get_ai_suggestion_for_action(suggestion_id).action_send()
        return self.get_ai_assistant_data()

    def action_ai_feedback_suggestion(self, suggestion_id, feedback_state):
        suggestion = self._get_ai_suggestion_for_action(suggestion_id)
        if feedback_state not in ('helpful', 'edited', 'unsafe'):
            raise UserError(_('La evaluacion seleccionada no es valida.'))
        suggestion._set_feedback(feedback_state)
        return self.get_ai_assistant_data()

    def action_create_ai_suggestion(self):
        self.ensure_one()
        text = self._ai_chat_completion(self._ai_build_conversation())
        suggestion = self.env['chatroom.ai.suggestion'].create_from_channel(self, text)
        return {
            'type': 'ir.actions.act_window', 'name': _('Sugerencia de IA'),
            'res_model': 'chatroom.ai.suggestion', 'res_id': suggestion.id,
            'views': [(False, 'form')], 'target': 'new',
        }

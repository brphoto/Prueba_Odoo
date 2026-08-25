# -*- coding: utf-8 -*-
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
            query = ' '.join((message.body or '') for message in self.message_ids.sorted('date')[-6:] if message.body)
            knowledge = self.env['ai.knowledge.base'].sudo().get_sales_context(self, query=query)
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
            'suggestion': {
                'id': suggestion.id,
                'text': suggestion.suggested_text,
                'state': suggestion.state,
                'intent': suggestion.intent or '',
                'confidence': suggestion.confidence,
            } if suggestion else False,
        }

    def action_ai_prepare_suggestion(self):
        self.ensure_one()
        text = self._ai_chat_completion(self._ai_build_conversation())
        suggestion = self.env['chatroom.ai.suggestion'].create_from_channel(self, text)
        return {
            'id': suggestion.id, 'text': suggestion.suggested_text,
            'state': suggestion.state, 'intent': suggestion.intent or '',
            'confidence': suggestion.confidence,
        }

    def action_ai_prepare_summary(self):
        self.ensure_one()
        self.action_ai_summarize()
        return self.ai_summary or ''

    def action_ai_classify_intent(self):
        self.ensure_one()
        self.ai_intent = self._ai_classify_intent()
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

    def action_create_ai_suggestion(self):
        self.ensure_one()
        text = self._ai_chat_completion(self._ai_build_conversation())
        suggestion = self.env['chatroom.ai.suggestion'].create_from_channel(self, text)
        return {
            'type': 'ir.actions.act_window', 'name': _('Sugerencia de IA'),
            'res_model': 'chatroom.ai.suggestion', 'res_id': suggestion.id,
            'views': [(False, 'form')], 'target': 'new',
        }

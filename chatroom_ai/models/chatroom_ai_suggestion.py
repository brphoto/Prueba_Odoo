# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ChatroomAiSuggestion(models.Model):
    _name = 'chatroom.ai.suggestion'
    _description = 'Sugerencia de IA de Chatroom'
    _order = 'create_date desc, id desc'

    name = fields.Char(string='Referencia', required=True, default=lambda self: _('Borrador IA'))
    channel_id = fields.Many2one('chatroom.channel', string='Conversación', required=True,
                                 ondelete='cascade', index=True)
    partner_id = fields.Many2one(related='channel_id.partner_id', string='Cliente', store=True)
    suggested_text = fields.Text(string='Respuesta sugerida', required=True)
    message_context = fields.Text(string='Contexto utilizado', readonly=True)
    source = fields.Selection([
        ('conversation', 'Conversación'), ('manual', 'Generación manual'),
    ], string='Fuente', required=True, default='conversation')
    source_detail = fields.Char(string='Detalle de fuente')
    intent = fields.Selection([
        ('consulta', 'Consulta'), ('venta', 'Venta'), ('soporte', 'Soporte'),
        ('queja', 'Queja'), ('otro', 'Otro'),
    ], string='Intención')
    confidence = fields.Float(string='Confianza estimada', digits=(5, 2),
                              help='Referencia informativa del proveedor o del agente; no activa envíos por sí sola.')
    safety_decision = fields.Selection([
        ('not_checked', 'No evaluada'), ('allowed', 'Permitida'),
        ('human_review', 'Revision humana'), ('blocked', 'Bloqueada'),
    ], string='Control de seguridad', default='not_checked', readonly=True,
       help='Resultado de los controles de consentimiento, horario, frecuencia y riesgo.')
    safety_reason = fields.Text(string='Motivo del control de seguridad', readonly=True)
    feedback_state = fields.Selection([
        ('pending', 'Sin valorar'), ('helpful', 'Util'),
        ('edited', 'Requirió edición'), ('unsafe', 'No usar'),
    ], string='Evaluación humana', default='pending', index=True,
       help='Permite medir la calidad real de las respuestas antes de ampliar la automatización.')
    feedback_notes = fields.Text(string='Observaciones de calidad')
    feedback_by = fields.Many2one('res.users', string='Evaluada por', readonly=True)
    feedback_at = fields.Datetime(string='Evaluada el', readonly=True)
    edited_by_human = fields.Boolean(string='Editada por humano', readonly=True)
    edit_count = fields.Integer(string='Ediciones', readonly=True)
    last_reviewed_at = fields.Datetime(string='Última revisión', readonly=True)
    state = fields.Selection([
        ('draft', 'Borrador'), ('approved', 'Aprobada'), ('rejected', 'Descartada'),
        ('sent', 'Enviada'), ('error', 'Error'),
    ], string='Estado', default='draft', required=True, index=True)
    rejection_reason = fields.Text(string='Motivo de descarte')
    error_message = fields.Text(string='Detalle del error', readonly=True)
    approved_by = fields.Many2one('res.users', string='Aprobada por', readonly=True)
    approved_at = fields.Datetime(string='Aprobada el', readonly=True)
    sent_by = fields.Many2one('res.users', string='Enviada por', readonly=True)
    sent_at = fields.Datetime(string='Enviada el', readonly=True)

    @api.model
    def create_from_channel(self, channel, text, source='conversation'):
        channel.ensure_one()
        return self.create({
            'name': _('IA - %s') % channel.display_name,
            'channel_id': channel.id,
            'suggested_text': text.strip(),
            'message_context': _('Últimos mensajes de la conversación (%s).') % len(channel.message_ids),
            'source': source,
            'source_detail': channel.display_name,
            'intent': channel.ai_intent or False,
        })

    def action_approve(self):
        for suggestion in self:
            if not suggestion.suggested_text.strip():
                raise UserError(_('La sugerencia no puede estar vacía.'))
            if suggestion.state not in ('draft', 'error'):
                continue
            suggestion.write({
                'state': 'approved', 'approved_by': self.env.user.id,
                'approved_at': fields.Datetime.now(), 'error_message': False,
                'last_reviewed_at': fields.Datetime.now(),
            })
        return True

    def action_reject(self):
        self.write({'state': 'rejected', 'rejection_reason': self[:1].rejection_reason or False})
        return True

    def _set_feedback(self, state):
        self.write({
            'feedback_state': state,
            'feedback_by': self.env.user.id,
            'feedback_at': fields.Datetime.now(),
        })
        if state == 'unsafe':
            channels = self.mapped('channel_id')
            channels.write({'ai_paused': True})
            if 'chatroom.notification' in self.env:
                for channel in channels:
                    user = channel.assigned_user_id or self.env.user
                    self.env['chatroom.notification'].sudo().create_deduplicated({
                        'name': _('IA pausada por respuesta insegura'),
                        'message': _('La conversacion %s quedo pausada para revision humana.') % channel.display_name,
                        'notification_type': 'ai',
                        'priority': '2',
                        'user_id': user.id,
                        'channel_id': channel.id,
                        'partner_id': channel.partner_id.id,
                        'res_model': 'chatroom.channel',
                        'res_id': channel.id,
                        'dedupe_key': 'ai-unsafe:%s' % channel.id,
                        'escalation_level': 2,
                    })
        return True

    def action_feedback_helpful(self):
        return self._set_feedback('helpful')

    def action_feedback_edited(self):
        return self._set_feedback('edited')

    def action_feedback_unsafe(self):
        return self._set_feedback('unsafe')

    def action_send(self):
        for suggestion in self:
            if suggestion.state != 'approved':
                raise UserError(_('Solo se puede enviar una sugerencia aprobada.'))
            try:
                suggestion.channel_id.with_context(
                    chatroom_ai_generated=True).action_send_text(suggestion.suggested_text)
            except Exception as exc:
                suggestion.write({'state': 'error', 'error_message': str(exc)})
                raise
            suggestion.write({
                'state': 'sent', 'sent_by': self.env.user.id,
                'sent_at': fields.Datetime.now(),
            })
        return True

    def action_generate(self):
        for suggestion in self:
            try:
                text = suggestion.channel_id._ai_chat_completion(
                    suggestion.channel_id._ai_build_conversation())
                suggestion.write({
                    'suggested_text': text, 'state': 'draft',
                    'error_message': False, 'intent': suggestion.channel_id.ai_intent or False,
                })
            except Exception as exc:
                suggestion.write({'state': 'error', 'error_message': str(exc)})
                raise UserError(_('No se pudo generar la sugerencia: %s') % exc)
        return True

    def action_open_channel(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': self.channel_id.display_name,
            'res_model': 'chatroom.channel', 'res_id': self.channel_id.id,
            'views': [(False, 'form')], 'target': 'current',
        }

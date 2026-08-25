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

    def action_send(self):
        for suggestion in self:
            if suggestion.state != 'approved':
                raise UserError(_('Solo se puede enviar una sugerencia aprobada.'))
            try:
                suggestion.channel_id.action_send_text(suggestion.suggested_text)
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

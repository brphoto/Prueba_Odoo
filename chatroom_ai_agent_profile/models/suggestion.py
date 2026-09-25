# -*- coding: utf-8 -*-
"""Bandeja «Para aprobar»: todos los borradores de la IA en una lista."""
from odoo import _, api, fields, models


class ChatroomAiSuggestion(models.Model):
    _inherit = 'chatroom.ai.suggestion'

    original_text = fields.Text(string='Texto original de la IA', readonly=True, copy=False)
    customer_question = fields.Text(string='El cliente escribió', compute='_compute_customer_question')
    waiting_minutes = fields.Integer(string='Esperando (min)', compute='_compute_customer_question')
    assigned_user_id = fields.Many2one(related='channel_id.assigned_user_id', string='Responsable')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.setdefault('original_text', vals.get('suggested_text'))
        return super().create(vals_list)

    def _compute_customer_question(self):
        Message = self.env['chatroom.message']
        now = fields.Datetime.now()
        for suggestion in self:
            inbound = Message.search([
                ('channel_id', '=', suggestion.channel_id.id), ('direction', '=', 'inbound'),
                ('create_date', '<=', suggestion.create_date or now)], order='id desc', limit=3)
            suggestion.customer_question = '\n'.join(
                message._ai_text() for message in inbound.sorted('id') if message._ai_text())[:600]
            suggestion.waiting_minutes = int(((now - suggestion.create_date).total_seconds() // 60)
                                             if suggestion.create_date else 0)

    def action_approve_and_send(self):
        """Un clic: aprueba, envía y, si se editó, la IA aprende la corrección."""
        Example = self.env['chatroom.ai.example'].sudo()
        for suggestion in self.filtered(lambda item: item.state in ('draft', 'approved', 'error')):
            text = (suggestion.suggested_text or '').strip()
            edited = bool(suggestion.original_text) and text != suggestion.original_text.strip()
            if suggestion.state != 'approved':
                suggestion.action_approve()
            suggestion.action_send()
            if edited and suggestion.customer_question:
                Example._learn(suggestion.customer_question, text, category=suggestion.intent or False,
                               line=suggestion.channel_id.whatsapp_number_id, ai_text=suggestion.original_text,
                               source='correction', company=suggestion.channel_id.company_id)
            if suggestion.feedback_state == 'pending':
                suggestion._set_feedback('edited' if edited else 'helpful')
            suggestion.channel_id.sudo().ai_list_state = 'ai'
        return True

    def action_open_chat(self):
        self.ensure_one()
        return self.channel_id.action_open_in_chat()

    def action_discard(self):
        self.action_reject()
        for suggestion in self:
            if suggestion.channel_id.ai_list_state == 'draft':
                suggestion.channel_id.sudo().ai_list_state = False
        return True

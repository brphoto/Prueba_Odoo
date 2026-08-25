# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError


class ChatroomAiKnowledgeTest(models.TransientModel):
    _name = 'chatroom.ai.knowledge.test'
    _description = 'Prueba local de conocimiento IA'

    question = fields.Text(string='Pregunta', required=True,
                           default='¿Qué información puede utilizar la IA?')
    channel_id = fields.Many2one('chatroom.channel', string='Conversación de referencia')
    partner_id = fields.Many2one('res.partner', string='Cliente de referencia')
    context_preview = fields.Text(string='Contexto recuperado', readonly=True)
    source_summary = fields.Text(string='Fuentes utilizadas', readonly=True)
    live_summary = fields.Text(string='Datos vivos consultados', readonly=True)
    estimated_input_tokens = fields.Integer(string='Tokens de entrada estimados', readonly=True)
    context_chars = fields.Integer(string='Caracteres de contexto', readonly=True)

    def action_preview(self):
        self.ensure_one()
        if not (self.question or '').strip():
            raise UserError(_('Escribe una pregunta para probar el conocimiento.'))
        details = self.env['ai.knowledge.base'].get_sales_context_details(
            self.channel_id, query=self.question, partner=self.partner_id)
        sources = details.get('sources') or []
        source_lines = [
            '- %s | categoría: %s | coincidencia: %s | fragmentos: %s' % (
                item['name'], item.get('category') or 'general',
                item.get('score', 0), item.get('chunks', 0))
            for item in sources
        ]
        live_lines = [item for item in details.get('live_sources', []) if item]
        self.write({
            'context_preview': details.get('context', ''),
            'source_summary': '\n'.join(source_lines) or _('No coincidió ningún manual indexado.'),
            'live_summary': '\n'.join('- %s' % item for item in live_lines) or _('No se consultaron datos vivos.'),
            'estimated_input_tokens': details.get('estimated_input_tokens', 0),
            'context_chars': details.get('context_chars', 0),
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Probar conocimiento IA'),
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }

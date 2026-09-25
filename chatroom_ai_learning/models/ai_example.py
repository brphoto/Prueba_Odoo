# -*- coding: utf-8 -*-
from odoo import _, api, fields, models

from .learning_utils import CATEGORIES, keyword_overlap

MAX_TEXT = 1500


class ChatroomAiExample(models.Model):
    """Respuesta aprobada por el equipo para un tipo de mensaje del cliente.

    La IA la recibe como ejemplo cuando llega un mensaje parecido: así imita
    lo que responde el equipo sin reentrenar ningún modelo.
    """
    _name = 'chatroom.ai.example'
    _description = 'Ejemplo aprendido'
    _order = 'last_used desc, id desc'
    _rec_name = 'customer_message'

    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Empresa', required=True,
                                 default=lambda self: self.env.company, index=True)
    line_id = fields.Many2one('chatroom.whatsapp.number', string='Línea', index=True, ondelete='set null',
                              help='Vacío: sirve para todas las líneas.')
    category = fields.Selection(CATEGORIES, string='Tipo de conversación', index=True)
    customer_message = fields.Text(string='Mensaje del cliente', required=True)
    ai_text = fields.Text(string='Lo que propuso la IA')
    approved_text = fields.Text(string='Respuesta aprobada', required=True)
    source = fields.Selection([
        ('correction', 'Corrección del equipo'),
        ('shadow', 'Modo sombra'),
        ('manual', 'Cargado a mano'),
    ], string='Origen', default='manual', required=True)
    inbound_message_id = fields.Many2one('chatroom.message', string='Mensaje de origen', ondelete='set null')
    use_count = fields.Integer(string='Veces usado', readonly=True)
    last_used = fields.Datetime(string='Último uso', readonly=True)

    @api.model
    def _learn(self, customer_message, approved_text, category=False, line=None, ai_text=False,
               source='correction', company=None, inbound_message=None):
        """Guarda (o actualiza) la respuesta aprobada para ese tipo de mensaje."""
        company = company or self.env.company
        customer_message = (customer_message or '').strip()[:MAX_TEXT]
        approved_text = (approved_text or '').strip()[:MAX_TEXT]
        candidates = self.search([
            ('company_id', '=', company.id), ('category', '=', category or False),
            ('line_id', '=', line.id if line else False),
        ], limit=200)
        for example in candidates:
            if keyword_overlap(customer_message, example.customer_message) >= 0.8:
                example.write({'approved_text': approved_text, 'ai_text': ai_text or example.ai_text,
                               'source': source, 'active': True})
                return example
        return self.create({
            'customer_message': customer_message, 'approved_text': approved_text,
            'ai_text': (ai_text or '')[:MAX_TEXT] or False, 'category': category or False,
            'line_id': line.id if line else False, 'source': source, 'company_id': company.id,
            'inbound_message_id': inbound_message.id if inbound_message else False,
        })

    @api.model
    def _find(self, query, category=False, line=None, company=None, limit=3, exclude_inbound=False):
        """Los ejemplos más parecidos al mensaje del cliente."""
        if not (query or '').strip():
            return self.browse()
        company = company or self.env.company
        domain = [('company_id', '=', company.id),
                  '|', ('line_id', '=', False), ('line_id', '=', line.id if line else False)]
        if exclude_inbound:
            domain.append(('inbound_message_id', '!=', exclude_inbound))
        scored = []
        for example in self.search(domain, limit=500):
            score = keyword_overlap(query, example.customer_message)
            if category and example.category == category:
                score += 0.15
            if line and example.line_id == line:
                score += 0.05
            if score >= 0.2:
                scored.append((score, example))
        scored.sort(key=lambda item: -item[0])
        return self.browse([example.id for _score, example in scored[:limit]])

    def _prompt_block(self):
        if not self:
            return ''
        self.sudo().write({'last_used': fields.Datetime.now()})
        for example in self.sudo():
            example.use_count += 1
        lines = [_('Ejemplos de respuestas aprobadas por el equipo para mensajes parecidos. '
                   'Imita su tono y enfoque; no copies datos que no correspondan a este cliente.')]
        for index, example in enumerate(self, start=1):
            lines.append(_('Ejemplo %(n)s\nCliente: %(customer)s\nRespuesta aprobada: %(answer)s') % {
                'n': index, 'customer': example.customer_message, 'answer': example.approved_text})
        return '\n\n'.join(lines)

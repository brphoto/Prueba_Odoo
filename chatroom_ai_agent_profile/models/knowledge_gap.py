# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.chatroom_ai_learning.models.learning_utils import CATEGORIES, keyword_overlap, tokens

KNOWLEDGE_CATEGORY = {'venta': 'sales', 'soporte': 'support', 'queja': 'support'}


class ChatroomAiKnowledgeGap(models.Model):
    """Pregunta de clientes que la IA no pudo responder con la información.

    Se agrupan las parecidas, se captura lo que respondió el equipo y, al
    aprobarla, se publica como conocimiento: así la base crece sola.
    """
    _name = 'chatroom.ai.knowledge.gap'
    _description = 'Vacío de conocimiento'
    _order = 'state_order, count desc, last_seen desc, id desc'
    _rec_name = 'question'

    question = fields.Text(string='Pregunta del cliente', required=True)
    company_id = fields.Many2one('res.company', string='Empresa', default=lambda self: self.env.company,
                                 required=True, index=True)
    profile_id = fields.Many2one('chatroom.ai.agent.profile', string='Perfil', ondelete='set null', index=True)
    category = fields.Selection(CATEGORIES, string='Tipo de conversación')
    count = fields.Integer(string='Veces preguntada', default=1)
    last_seen = fields.Datetime(string='Última vez', default=fields.Datetime.now)
    channel_id = fields.Many2one('chatroom.channel', string='Última conversación', ondelete='set null')
    inbound_message_id = fields.Many2one('chatroom.message', string='Mensaje', ondelete='set null')
    state = fields.Selection([
        ('open', 'Sin respuesta'),
        ('proposed', 'Respuesta propuesta'),
        ('published', 'Publicada'),
        ('ignored', 'Descartada'),
    ], string='Estado', default='open', required=True, index=True)
    state_order = fields.Integer(compute='_compute_state_order', store=True)
    answer = fields.Text(string='Respuesta', help='Lo que respondió el equipo; puedes editarla antes de publicar.')
    answered_by = fields.Many2one('res.users', string='Respondió', readonly=True)
    knowledge_id = fields.Many2one('ai.knowledge.base', string='Conocimiento publicado', readonly=True,
                                   ondelete='set null')

    @api.depends('state')
    def _compute_state_order(self):
        order = {'proposed': 0, 'open': 1, 'published': 2, 'ignored': 3}
        for gap in self:
            gap.state_order = order.get(gap.state, 9)

    @api.model
    def _register_question(self, question, channel=None, inbound=None, category=False, profile=None):
        """Agrupa con una pregunta parecida o crea una nueva."""
        question = (question or '').strip()[:500]
        if len(tokens(question)) < 2:
            return self.browse()
        company = channel.company_id if channel else self.env.company
        values = {'last_seen': fields.Datetime.now(), 'channel_id': channel.id if channel else False,
                  'inbound_message_id': inbound.id if inbound else False}
        for gap in self.sudo().search([('company_id', '=', company.id), ('state', 'in', ('open', 'proposed'))],
                                      limit=300):
            if keyword_overlap(question, gap.question) >= 0.6:
                if gap.inbound_message_id != inbound or not inbound:
                    values['count'] = gap.count + 1
                gap.write(values)
                return gap
        return self.sudo().create(dict(values, question=question, company_id=company.id,
                                       category=category or False,
                                       profile_id=profile.id if profile else False))

    @api.model
    def _capture_answer(self, channel, message):
        """La primera respuesta humana tras un vacío queda como propuesta."""
        gap = self.sudo().search([
            ('channel_id', '=', channel.id), ('state', '=', 'open'),
            ('last_seen', '>=', fields.Datetime.now() - timedelta(hours=48)),
        ], order='last_seen desc, id desc', limit=1)
        if gap and message.body:
            gap.write({'answer': message.body.strip()[:2000], 'answered_by': message.sender_user_id.id,
                       'state': 'proposed'})
        return gap

    def write(self, vals):
        # Escribir una respuesta en un vacío abierto la deja propuesta.
        if vals.get('answer') and 'state' not in vals:
            opened = self.filtered(lambda gap: gap.state == 'open')
            super(ChatroomAiKnowledgeGap, opened).write(dict(vals, state='proposed'))
            return super(ChatroomAiKnowledgeGap, self - opened).write(vals)
        return super().write(vals)

    def action_publish(self):
        """Publica la respuesta como conocimiento y como ejemplo aprobado."""
        Knowledge = self.env['ai.knowledge.base'].sudo()
        for gap in self:
            answer = (gap.answer or '').strip()
            if not answer:
                raise UserError(_('Escribe la respuesta antes de publicarla.'))
            content = _('Pregunta: %(q)s\nRespuesta: %(a)s') % {'q': gap.question.strip(), 'a': answer}
            knowledge = gap.knowledge_id
            if knowledge:
                knowledge.write({'source_text': content})
            else:
                knowledge = Knowledge.create({
                    'name': _('FAQ: %s') % gap.question.strip()[:70],
                    'source_type': 'text', 'source_text': content, 'knowledge_format': 'faq',
                    'category': KNOWLEDGE_CATEGORY.get(gap.category, 'general'),
                    'keyword_tags': ', '.join(sorted(tokens(gap.question))[:12]),
                    'company_id': gap.company_id.id,
                })
            knowledge.action_index()
            knowledge.action_publish()
            self.env['chatroom.ai.example'].sudo()._learn(
                gap.question, answer, category=gap.category, source='manual', company=gap.company_id)
            gap.write({'state': 'published', 'knowledge_id': knowledge.id})
        return True

    def action_ignore(self):
        self.write({'state': 'ignored'})
        return True

    def action_reopen(self):
        self.write({'state': 'proposed' if self[:1].answer else 'open'})
        return True

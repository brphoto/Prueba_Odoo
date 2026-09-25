# -*- coding: utf-8 -*-
from datetime import timedelta

from markupsafe import Markup

from odoo import _, fields, models
from odoo.exceptions import UserError

from odoo.addons.chatroom_ai_learning.models.learning_utils import keyword_overlap, normalize

BATCH = 30


class ChatroomAiExample(models.Model):
    _inherit = 'chatroom.ai.example'

    source = fields.Selection(selection_add=[('history', 'Historial de chats')], ondelete={'history': 'set default'})


class ChatroomAiKnowledgeGap(models.Model):
    _inherit = 'chatroom.ai.knowledge.gap'

    source = fields.Selection([
        ('conversation', 'La IA no supo responder'),
        ('history', 'Propuesta desde chats anteriores'),
    ], string='Origen', default='conversation', required=True)


class ChatroomAiHistoryImport(models.TransientModel):
    """Aprende de lo que el equipo ya respondió por WhatsApp.

    Cada respuesta de un asesor a un cliente se guarda como ejemplo aprobado;
    la IA propone además preguntas frecuentes generales (sin datos personales)
    para publicar en la base de conocimiento, y casos de prueba.
    """
    _name = 'chatroom.ai.history.import'
    _description = 'Aprender de conversaciones anteriores'

    profile_id = fields.Many2one('chatroom.ai.agent.profile', string='Perfil', required=True,
                                 default=lambda self: self.env['chatroom.ai.agent.profile']._for_line())
    date_from = fields.Date(string='Desde', required=True,
                            default=lambda self: fields.Date.context_today(self) - timedelta(days=90))
    max_conversations = fields.Integer(string='Máximo de conversaciones', default=200)
    create_examples = fields.Boolean(string='Guardar las respuestas como ejemplos', default=True)
    propose_faq = fields.Boolean(string='Proponer preguntas frecuentes (usa IA)', default=True)
    create_cases = fields.Boolean(string='Crear casos de prueba con las más frecuentes', default=True)
    max_cases = fields.Integer(string='Máximo de casos', default=10)
    state = fields.Selection([('draft', 'Configurar'), ('done', 'Listo')], default='draft')
    result_html = fields.Html(string='Resultado', readonly=True, sanitize=False)

    def _pairs(self):
        """Pares (lo que escribió el cliente, lo que respondió una persona)."""
        self.ensure_one()
        since = fields.Datetime.to_datetime(self.date_from)
        channels = self.env['chatroom.channel'].sudo().search([
            ('channel_type', '=', 'whatsapp'), ('last_message_date', '>=', since),
        ], order='last_message_date desc', limit=max(1, self.max_conversations))
        pairs = []
        for channel in channels:
            burst = []
            for message in channel.message_ids.filtered(lambda item: item.date >= since).sorted('id'):
                if message.direction == 'inbound':
                    if message._ai_text():
                        burst.append(message._ai_text())
                    continue
                human = (message.body and message.message_type == 'text' and message.sender_user_id
                         and not message.sender_user_id._is_superuser() and not message.ai_generated)
                if burst and human:
                    question = ' '.join(burst)[-600:].strip()
                    answer = message.body.strip()[:800]
                    if (len(normalize(question)) >= 12 and len(answer) >= 15
                            and not self.profile_id._local_reply(question)):
                        pairs.append({'question': question, 'answer': answer, 'channel': channel,
                                      'message': message})
                if message.direction == 'outbound':
                    burst = []
        return pairs

    def _extract_faq(self, pairs):
        """La IA agrupa los pares en preguntas frecuentes generales."""
        faq = []
        service = self.env['chatroom.ai.service']
        for start in range(0, len(pairs), BATCH):
            chunk = pairs[start:start + BATCH]
            listing = '\n\n'.join('%s. Cliente: %s\nEquipo: %s' % (index, pair['question'], pair['answer'])
                                  for index, pair in enumerate(chunk, start=1))
            data = service.complete_json([
                {'role': 'system', 'content': _(
                    'Recibes pares de mensajes de clientes y respuestas del equipo de una empresa. Extrae '
                    'PREGUNTAS FRECUENTES GENERALES, útiles para cualquier cliente: políticas, horarios, '
                    'precios o condiciones generales, procesos. Omite todo lo personal o de un caso puntual '
                    '(números de pedido o guía, nombres, direcciones, estado de un envío concreto). Une las '
                    'parecidas y cuenta cuántas veces aparecen. Redacta la respuesta oficial solo con lo que '
                    'dijo el equipo, sin agregar datos. Devuelve SOLO JSON: {"faq": [{"pregunta": "...", '
                    '"respuesta": "...", "veces": 1}]}')},
                {'role': 'user', 'content': listing},
            ], required_keys=('faq',), task_type='summary', timeout=120)
            for item in data.get('faq') or []:
                if isinstance(item, dict) and item.get('pregunta') and item.get('respuesta'):
                    try:
                        count = max(1, int(item.get('veces') or 1))
                    except (TypeError, ValueError):
                        count = 1
                    faq.append({'question': str(item['pregunta']).strip()[:500],
                                'answer': str(item['respuesta']).strip()[:2000], 'count': count})
        # Une lo repetido entre lotes.
        merged = []
        for item in sorted(faq, key=lambda entry: -entry['count']):
            same = next((entry for entry in merged if keyword_overlap(entry['question'], item['question']) >= 0.6), None)
            if same:
                same['count'] += item['count']
            else:
                merged.append(dict(item))
        return merged

    def action_run(self):
        self.ensure_one()
        pairs = self._pairs()
        if not pairs:
            raise UserError(_('No hay conversaciones con respuestas del equipo en ese periodo.'))
        company = self.profile_id.company_id or self.env.company
        examples = faq_created = cases = 0
        if self.create_examples:
            Example = self.env['chatroom.ai.example'].sudo()
            learned = Example.browse()
            for pair in pairs:
                learned |= Example._learn(pair['question'], pair['answer'], line=pair['channel'].whatsapp_number_id,
                                          source='history', company=company)
            examples = len(learned)
        faq = []
        if self.propose_faq:
            faq = self._extract_faq(pairs)
            Gap = self.env['chatroom.ai.knowledge.gap'].sudo()
            existing = Gap.search([('company_id', '=', company.id)])
            for item in faq:
                if any(keyword_overlap(item['question'], gap.question) >= 0.6 for gap in existing):
                    continue
                existing |= Gap.create({
                    'question': item['question'], 'answer': item['answer'], 'count': item['count'],
                    'state': 'proposed', 'source': 'history', 'company_id': company.id,
                    'profile_id': self.profile_id.id})
                faq_created += 1
        if self.create_cases and faq:
            Case = self.env['chatroom.ai.eval.case'].sudo()
            for item in faq[:max(0, self.max_cases)]:
                if Case.search_count([('name', '=', item['question'][:60])]):
                    continue
                Case.create({'name': item['question'][:60], 'transcript': _('Cliente: %s') % item['question'],
                             'expected': 'reply', 'reference_answer': item['answer'],
                             'company_id': company.id})
                cases += 1
        rows = [
            (_('Respuestas del equipo analizadas'), len(pairs)),
            (_('Ejemplos aprobados guardados'), examples),
            (_('Preguntas frecuentes propuestas para publicar'), faq_created),
            (_('Casos de prueba creados'), cases),
        ]
        self.write({'state': 'done', 'result_html': Markup('<ul class="mb-0">%s</ul>') % Markup('').join(
            Markup('<li><b>%s</b>: %s</li>') % (label, value) for label, value in rows)})
        return {'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': self.id,
                'view_mode': 'form', 'views': [(False, 'form')], 'target': 'new'}

    def action_open_proposals(self):
        action = self.env['ir.actions.act_window']._for_xml_id('chatroom_ai_agent_profile.action_knowledge_gap')
        action['domain'] = [('source', '=', 'history'), ('state', '=', 'proposed')]
        action['context'] = {}
        return action

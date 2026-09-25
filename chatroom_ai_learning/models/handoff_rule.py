# -*- coding: utf-8 -*-
from odoo import _, api, fields, models

from .learning_utils import CATEGORIES, contains_phrase, split_list


class ChatroomAiHandoffRule(models.Model):
    """Cuándo la IA deja de responder y pasa la conversación a una persona."""
    _name = 'chatroom.ai.handoff.rule'
    _description = 'Regla de traspaso a una persona'
    _order = 'sequence, id'

    name = fields.Char(string='Nombre', required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Empresa', default=lambda self: self.env.company,
                                 help='Vacío: aplica a todas las empresas.')
    trigger = fields.Selection([
        ('keywords', 'El cliente dice ciertas palabras'),
        ('intent', 'Tipo de conversación'),
        ('negative', 'El cliente está molesto'),
        ('urgency', 'Urgencia alta'),
        ('low_confidence', 'La IA tiene poca confianza'),
    ], string='Cuándo', required=True, default='keywords')
    keywords = fields.Text(
        string='Palabras o frases',
        help='Una por línea o separadas por coma. Se buscan como palabras completas, '
             'sin importar mayúsculas ni tildes.')
    intent = fields.Selection(CATEGORIES, string='Tipo de conversación')
    min_confidence = fields.Float(string='Confianza mínima', default=0.5,
                                  help='Por debajo de este valor la conversación pasa a una persona.')
    negative_requires_urgency = fields.Boolean(
        string='Solo si además es urgente',
        help='Para «El cliente está molesto»: pasa a una persona solo si también hay urgencia alta. '
             'Útil cuando muchos clientes escriben molestos por algo que la IA puede resolver.')
    pause_ai = fields.Boolean(string='Pausar la IA en la conversación', default=True)
    notify = fields.Selection([
        ('assigned', 'Responsable de la conversación'),
        ('line', 'Equipo de la línea'),
        ('managers', 'Administradores de Chatroom'),
    ], string='Avisar a', default='assigned', required=True)
    customer_message = fields.Text(
        string='Mensaje al cliente',
        default=lambda self: _('Gracias por escribirnos. Te comunico con una persona de nuestro '
                               'equipo que te responderá en breve.'),
        help='Vacío: no se le envía nada al cliente.')
    post_summary = fields.Boolean(string='Dejar resumen para el equipo', default=True)
    match_count = fields.Integer(string='Veces aplicada', readonly=True)
    last_match = fields.Datetime(string='Última vez', readonly=True)

    def _company_domain(self, company):
        return ['|', ('company_id', '=', False), ('company_id', '=', company.id)]

    @api.model
    def _match_text(self, text, company=None):
        """(regla, motivo) si el mensaje del cliente activa una regla de palabras."""
        company = company or self.env.company
        for rule in self.search([('trigger', '=', 'keywords')] + self._company_domain(company)):
            for phrase in split_list(rule.keywords):
                if contains_phrase(text, phrase):
                    return rule, _('El cliente mencionó «%s».') % phrase
        return self.browse(), False

    @api.model
    def _match_draft(self, draft, company=None):
        """(regla, motivo) si la evaluación de la IA activa una regla."""
        company = company or self.env.company
        labels = dict(CATEGORIES)
        for rule in self.search([('trigger', '!=', 'keywords')] + self._company_domain(company)):
            if rule.trigger == 'intent' and draft.get('intent') and draft['intent'] == rule.intent:
                return rule, _('Conversación de tipo «%s».') % labels.get(rule.intent, rule.intent)
            if (rule.trigger == 'negative' and draft.get('sentiment') == 'negative'
                    and (not rule.negative_requires_urgency or draft.get('urgency') in ('high', 'critical'))):
                return rule, _('El cliente parece molesto.')
            if rule.trigger == 'urgency' and draft.get('urgency') in ('high', 'critical'):
                return rule, _('El cliente indica urgencia.')
            if rule.trigger == 'low_confidence' and draft.get('confidence', 1.0) < rule.min_confidence:
                return rule, _('La IA tiene poca confianza (%.0f%%).') % (draft['confidence'] * 100)
        return self.browse(), False

    def _register_match(self):
        for rule in self.sudo():
            rule.write({'match_count': rule.match_count + 1, 'last_match': fields.Datetime.now()})

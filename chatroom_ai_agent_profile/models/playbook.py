# -*- coding: utf-8 -*-
import json
import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.chatroom_ai_learning.models.learning_utils import CATEGORIES, normalize


def slug(text, size=30):
    value = re.sub(r'[^a-z0-9]+', '_', normalize(text or '')).strip('_')
    return value[:size] or 'dato'


def load_data(raw):
    try:
        data = json.loads(raw or '{}')
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


class ChatroomAiAgentPlaybook(models.Model):
    """Qué datos reunir según lo que necesita el cliente y qué hacer después."""
    _name = 'chatroom.ai.agent.playbook'
    _description = 'Guion del agente IA'
    _order = 'sequence, id'

    name = fields.Char(string='Guion', required=True)
    code = fields.Char(string='Código', compute='_compute_code', store=True, readonly=False, required=True, precompute=True,
                       help='Identificador que usa la IA para indicar qué guion aplica.')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    profile_id = fields.Many2one('chatroom.ai.agent.profile', string='Perfil', required=True,
                                 ondelete='cascade', index=True)
    when_to_use = fields.Text(string='Cuándo aplica', required=True,
                              help='Ej.: «Cuando el cliente quiere comprar o pedir una cotización».')
    intent = fields.Selection(CATEGORIES, string='Tipo de conversación')
    goal = fields.Text(string='Objetivo', help='Para qué se reúnen estos datos.')
    field_ids = fields.One2many('chatroom.ai.agent.playbook.field', 'playbook_id', string='Datos a reunir',
                                copy=True)
    on_complete = fields.Selection([
        ('continue', 'La IA sigue atendiendo'),
        ('lead', 'Crear oportunidad en CRM y seguir'),
        ('handoff', 'Pasar a una persona con los datos'),
        ('quote', 'Preparar cotización en borrador y pasar a una persona'),
        ('send_quote', 'Enviar la cotización al cliente con enlace para aceptarla y pagar'),
        ('meeting', 'Agendar la cita en el calendario y pasar a una persona'),
        ('activity', 'Crear tarea para el equipo y pasar a una persona'),
    ], string='Al completar los datos', default='handoff', required=True)

    _code_uniq = models.UniqueIndex('(profile_id, code)', 'Ya existe un guion con ese código en el perfil.')

    @api.depends('name')
    def _compute_code(self):
        for playbook in self:
            if not playbook.code:
                playbook.code = slug(playbook.name, 24)

    @api.constrains('code')
    def _check_code(self):
        for playbook in self:
            if not re.fullmatch(r'[a-z0-9_]{2,30}', playbook.code or ''):
                raise ValidationError(_('El código solo admite minúsculas, números y «_» (2 a 30).'))

    def _required(self):
        self.ensure_one()
        return self.field_ids.filtered('required')

    def _missing(self, data):
        self.ensure_one()
        return self._required().filtered(lambda field: not str(data.get(field.key) or '').strip())

    def _prompt_block(self):
        self.ensure_one()
        lines = ['[%s] %s — %s: %s' % (self.code, self.name, _('cuándo aplica'), self.when_to_use.strip())]
        if self.goal:
            lines.append('   %s: %s' % (_('objetivo'), self.goal.strip()))
        for field in self.field_ids:
            lines.append('   - %s: %s%s%s%s' % (
                field.key, field.label, _(' (obligatorio)') if field.required else _(' (opcional)'),
                ' — %s' % field.hint if field.hint else '',
                _(' — opciones: %s') % ' / '.join(field._option_list()) if field._option_list() else ''))
        return '\n'.join(lines)

    def _state_block(self, data, done=False):
        self.ensure_one()
        known = {key: value for key, value in data.items() if value}
        if done:
            return _('Guion «%(name)s» COMPLETADO con: %(data)s. No vuelvas a pedir estos datos.') % {
                'name': self.name, 'data': json.dumps(known, ensure_ascii=False)}
        missing = self._missing(data)
        return _('Guion en curso: [%(code)s]. Datos ya obtenidos: %(data)s. Faltan: %(missing)s.') % {
            'code': self.code, 'data': json.dumps(known, ensure_ascii=False),
            'missing': ', '.join(missing.mapped('label')) or _('ninguno obligatorio')}

    def _summary(self, data):
        self.ensure_one()
        return '\n'.join('- %s: %s' % (field.label, data.get(field.key) or '—') for field in self.field_ids)

    def _progress(self, data, done=False):
        self.ensure_one()
        required = self._required()
        filled = len(required) - len(self._missing(data))
        return {'id': self.id, 'name': self.name, 'filled': filled, 'total': len(required),
                'done': bool(done), 'missing': self._missing(data).mapped('label')}

    @api.model
    def _said_by_customer(self, value, evidence):
        """Un dato solo vale si sus palabras aparecen en lo que dijo el cliente.

        Con IA real el modelo llegó a anotar «nombre: cliente» sin que el
        cliente lo dijera, y el guion se daba por completo. Sin evidencia
        (casos sin conversación) se acepta.
        """
        if evidence is None:
            return True
        said = normalize(evidence)
        words = [word for word in re.findall(r'[a-z0-9]+', normalize(value)) if len(word) >= 3 or word.isdigit()]
        return not words or any(word in said for word in words)

    @api.model
    def _advance(self, playbooks, current, data, done, draft):
        """Aplica lo que la IA reconoció en la respuesta.

        :return: (guion, datos, completado, recién_completado)
        """
        # El modelo a veces copia el código como aparece en el prompt
        # («[cotizacion]») o con tildes: se normaliza y, si igual no coincide,
        # los datos van al guion en curso en lugar de perderse.
        raw_code = (draft.get('playbook_code') or '').strip()
        code = slug(raw_code) if raw_code else ''
        chosen = playbooks.filtered(lambda playbook: playbook.code == code)[:1] if code else current
        chosen = chosen or current
        if not chosen:
            return current, data, done, False
        if chosen != current:
            data, done = {}, False
        valid = set(chosen.field_ids.mapped('key'))
        # Un dato con opciones es una clasificación, no una cita: el cliente
        # dice «carro» y la IA elige «Vehicular» de la lista.
        options = {field.key: {normalize(option): option for option in field._option_list()}
                   for field in chosen.field_ids}
        data = dict(data)
        for key, value in (draft.get('collected') or {}).items():
            if key not in valid:
                continue
            option = options[key].get(normalize(value))
            if option:
                data[key] = option
            elif self._said_by_customer(value, draft.get('evidence')):
                data[key] = value
        newly_done = not done and bool(chosen._required() or data) and not chosen._missing(data)
        return chosen, data, done or newly_done, newly_done


    def _options_for(self, data, asked_key='', reply=''):
        """Opciones (botones) del dato que la respuesta le pide al cliente."""
        self.ensure_one()
        missing = self.field_ids.filtered(lambda field: not data.get(field.key) and field._option_list())
        field = missing.filtered(lambda item: asked_key and item.key in (asked_key, slug(asked_key)))[:1]
        if not field and not asked_key:
            # El modelo no lo dijo: el dato con opciones que la respuesta nombra.
            text = normalize(reply)
            field = missing.filtered(lambda item: normalize(item.label) in text
                                     or item.key.replace('_', ' ') in text)[:1]
        return field._option_list() if field else []


class ChatroomAiAgentPlaybookField(models.Model):
    _name = 'chatroom.ai.agent.playbook.field'
    _description = 'Dato a reunir en un guion'
    _order = 'sequence, id'

    playbook_id = fields.Many2one('chatroom.ai.agent.playbook', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    label = fields.Char(string='Dato', required=True)
    key = fields.Char(string='Clave', compute='_compute_key', store=True, readonly=False, required=True,
                      precompute=True)
    required = fields.Boolean(string='Obligatorio', default=True)
    hint = fields.Char(string='Pista para la IA', help='Ej.: «año de 4 dígitos», «ciudad y sector».')
    options = fields.Char(
        string='Opciones (botones)',
        help='Separadas por coma. Cuando la IA pide este dato, el cliente elige con botones de WhatsApp '
             '(hasta 3) o una lista (hasta 10) en vez de escribir.')

    def _option_list(self):
        self.ensure_one()
        return [option.strip() for option in (self.options or '').split(',') if option.strip()][:10]

    _key_uniq = models.UniqueIndex('(playbook_id, key)', 'Ese dato ya está en el guion.')

    @api.depends('label')
    def _compute_key(self):
        for field in self:
            if not field.key:
                field.key = slug(field.label)

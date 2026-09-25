# -*- coding: utf-8 -*-
import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

SHORTCUT_RE = re.compile(r'^[a-z0-9_-]{2,30}$')

# Variables que se pueden escribir en la instrucción. Se documentan en el
# formulario para que el administrador no tenga que adivinarlas.
PROMPT_VARIABLES = (
    ('{cliente}', 'Nombre del cliente'),
    ('{empresa}', 'Nombre de tu empresa'),
    ('{agente}', 'Nombre del agente que ejecuta la acción'),
    ('{linea}', 'Línea de WhatsApp de la conversación'),
    ('{ultimo_mensaje}', 'Último mensaje del cliente'),
    ('{borrador}', 'Lo que el agente escribió en el compositor'),
)

TONE_INSTRUCTIONS = {
    'formal': 'Usa un tono formal y profesional, tratando de usted.',
    'friendly': 'Usa un tono cercano y cálido, sin perder profesionalismo.',
    'brief': 'Sé muy breve: una o dos frases, directo al punto.',
    'empathetic': (
        'Usa un tono empático: reconoce la molestia del cliente, discúlpate '
        'si corresponde y propón un siguiente paso concreto.'),
}

LANGUAGE_INSTRUCTIONS = {
    'auto': 'Responde en el mismo idioma que usa el cliente.',
    'es': 'Responde en español.',
    'en': 'Responde en inglés.',
    'pt': 'Responde en portugués.',
}


class ChatroomAiQuickAction(models.Model):
    """Acción de IA configurable que el agente ejecuta desde el chat.

    Reemplaza las tres opciones fijas del asistente (respuesta, resumen e
    intención) por un catálogo que el administrador puede ampliar: cada
    acción tiene su instrucción, qué contexto usa (conocimiento, memoria,
    catálogo, historial del cliente) y qué hace con el resultado.
    """
    _name = 'chatroom.ai.quick.action'
    _description = 'Acción rápida de IA'
    _order = 'sequence, name'

    name = fields.Char(string='Nombre', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    icon = fields.Char(
        string='Icono', default='fa-magic',
        help='Icono de Font Awesome, por ejemplo fa-magic, fa-tag, fa-money.')
    shortcut = fields.Char(
        string='Atajo',
        help='Palabra para ejecutarla escribiendo /atajo en el compositor '
             '(minúsculas, sin espacios). Ej.: precio → /precio')
    description = fields.Char(
        string='Descripción', translate=True,
        help='Frase corta que ve el agente para saber cuándo usarla.')
    company_id = fields.Many2one(
        'res.company', string='Empresa', default=lambda self: self.env.company, index=True,
        help='Vacío: disponible en todas las empresas.')

    instruction = fields.Text(
        string='Instrucción para la IA', required=True, translate=True,
        help='Qué debe hacer la IA. Puedes usar variables como {cliente} o {borrador}.')
    output_mode = fields.Selection([
        ('reply', 'Borrador de respuesta'),
        ('rewrite', 'Reescribir mi borrador'),
        ('note', 'Nota interna en la conversación'),
        ('summary', 'Resumen interno'),
        ('intent', 'Clasificar intención'),
    ], string='Qué hace con el resultado', required=True, default='reply',
        help='Borrador de respuesta: queda para revisar, aprobar y enviar.\n'
             'Reescribir mi borrador: reemplaza el texto del compositor.\n'
             'Nota interna: se guarda en el chat, no se envía al cliente.\n'
             'Resumen interno: se muestra en el panel.\n'
             'Clasificar intención: actualiza la intención de la conversación.')

    use_knowledge = fields.Boolean(
        string='Base de conocimiento', default=True,
        help='Manuales y políticas publicados en la base de conocimiento.')
    use_memory = fields.Boolean(
        string='Memoria del cliente', default=True,
        help='Datos que la empresa guardó sobre este cliente.')
    use_catalog = fields.Boolean(
        string='Catálogo con precio y stock', default=False,
        help='Productos que coinciden con lo que pregunta el cliente, con '
             'precio y disponibilidad consultados en el momento.')
    use_customer_history = fields.Boolean(
        string='Pedidos y facturas del cliente', default=False,
        help='Últimos pedidos y facturas pendientes del cliente.')
    history_messages = fields.Integer(
        string='Mensajes de la conversación', default=0,
        help='Cuántos mensajes recientes lee la IA. 0 = el valor general de Ajustes.')

    tone = fields.Selection([
        ('default', 'El de la línea o el general'),
        ('formal', 'Formal'),
        ('friendly', 'Cercano'),
        ('brief', 'Muy breve'),
        ('empathetic', 'Empático'),
    ], string='Tono', default='default', required=True)
    language = fields.Selection([
        ('auto', 'El del cliente'),
        ('es', 'Español'),
        ('en', 'Inglés'),
        ('pt', 'Portugués'),
    ], string='Idioma', default='auto', required=True)
    max_words = fields.Integer(
        string='Máximo de palabras', default=0, help='0 = sin límite.')

    line_ids = fields.Many2many(
        'chatroom.whatsapp.number', 'chatroom_ai_quick_action_line_rel',
        'action_id', 'line_id', string='Solo en estas líneas',
        help='Vacío: disponible en todas las líneas.')
    group_ids = fields.Many2many(
        'res.groups', 'chatroom_ai_quick_action_group_rel',
        'action_id', 'group_id', string='Solo para estos grupos',
        help='Vacío: disponible para todos los agentes.')

    use_count = fields.Integer(string='Veces usada', readonly=True, copy=False)
    last_used = fields.Datetime(string='Último uso', readonly=True, copy=False)
    suggestion_ids = fields.One2many(
        'chatroom.ai.suggestion', 'quick_action_id', string='Borradores generados')
    suggestion_count = fields.Integer(compute='_compute_quality', string='Borradores')
    sent_count = fields.Integer(compute='_compute_quality', string='Enviados')
    helpful_count = fields.Integer(compute='_compute_quality', string='Útiles')
    edited_count = fields.Integer(compute='_compute_quality', string='Editados')
    unsafe_count = fields.Integer(compute='_compute_quality', string='No seguros')
    helpful_rate = fields.Float(
        compute='_compute_quality', string='% útiles',
        help='Borradores marcados como útiles sobre los evaluados.')
    edit_rate = fields.Float(
        compute='_compute_quality', string='% editados',
        help='Borradores que el agente tuvo que corregir: si es alto, conviene '
             'mejorar la instrucción.')
    variables_help = fields.Text(compute='_compute_variables_help')

    _shortcut_company_uniq = models.UniqueIndex(
        '(shortcut, COALESCE(company_id, 0)) WHERE shortcut IS NOT NULL AND active',
        'Ya existe otra acción activa con ese atajo.',
    )

    @api.constrains('shortcut')
    def _check_shortcut(self):
        for action in self:
            if action.shortcut and not SHORTCUT_RE.match(action.shortcut):
                raise ValidationError(_(
                    'El atajo «%s» debe tener entre 2 y 30 caracteres en minúsculas, '
                    'números, guion o guion bajo, sin espacios.') % action.shortcut)

    @api.onchange('shortcut')
    def _onchange_shortcut(self):
        if self.shortcut:
            self.shortcut = re.sub(r'[^a-z0-9_-]', '', self.shortcut.strip().lstrip('/').lower())

    def _compute_variables_help(self):
        text = '\n'.join('%s  →  %s' % item for item in PROMPT_VARIABLES)
        for action in self:
            action.variables_help = text

    @api.depends('suggestion_ids.state', 'suggestion_ids.feedback_state')
    def _compute_quality(self):
        stats = {action.id: dict.fromkeys(
            ('total', 'sent', 'helpful', 'edited', 'unsafe'), 0) for action in self}
        if self.ids:
            groups = self.env['chatroom.ai.suggestion'].sudo()._read_group(
                [('quick_action_id', 'in', self.ids)],
                ['quick_action_id', 'state', 'feedback_state'], ['__count'])
            for action, state, feedback, count in groups:
                row = stats[action.id]
                row['total'] += count
                if state == 'sent':
                    row['sent'] += count
                if feedback in ('helpful', 'edited', 'unsafe'):
                    row[feedback] += count
        for action in self:
            row = stats.get(action.id) or dict.fromkeys(
                ('total', 'sent', 'helpful', 'edited', 'unsafe'), 0)
            rated = row['helpful'] + row['edited'] + row['unsafe']
            action.suggestion_count = row['total']
            action.sent_count = row['sent']
            action.helpful_count = row['helpful']
            action.edited_count = row['edited']
            action.unsafe_count = row['unsafe']
            action.helpful_rate = (100.0 * row['helpful'] / rated) if rated else 0.0
            action.edit_rate = (100.0 * row['edited'] / rated) if rated else 0.0

    def action_view_suggestions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Borradores de «%s»') % self.name,
            'res_model': 'chatroom.ai.suggestion',
            'view_mode': 'list,form',
            'domain': [('quick_action_id', '=', self.id)],
        }

    # ------------------------------------------------------------------
    # Disponibilidad
    # ------------------------------------------------------------------
    def _is_available_for(self, channel, user=None):
        self.ensure_one()
        user = user or self.env.user
        if not self.active:
            return False
        if self.company_id and self.company_id != channel.company_id:
            return False
        if self.line_ids and channel.whatsapp_number_id not in self.line_ids:
            return False
        # sudo solo para comparar grupos: un agente no puede leer res.groups.
        # Crons y procesos internos (superusuario) pueden usar cualquier acción.
        is_superuser = self.env.su and user == self.env.user
        if self.sudo().group_ids and not is_superuser \
                and not (self.sudo().group_ids & user.sudo().all_group_ids):
            return False
        return True

    @api.model
    def _available_for(self, channel, user=None):
        actions = self.search([
            '|', ('company_id', '=', False), ('company_id', '=', channel.company_id.id),
        ])
        return actions.filtered(lambda action: action._is_available_for(channel, user))

    def _to_ui(self):
        return [{
            'id': action.id,
            'name': action.name,
            'icon': action.icon or 'fa-magic',
            'shortcut': action.shortcut or '',
            'description': action.description or '',
            'output_mode': action.output_mode,
        } for action in self]

    # ------------------------------------------------------------------
    # Instrucción final
    # ------------------------------------------------------------------
    def _render_instruction(self, channel, draft_text=''):
        """Instrucción con las variables reemplazadas y las reglas de tono,
        idioma y largo que eligió el administrador."""
        self.ensure_one()
        last_inbound = channel.message_ids.filtered(
            lambda message: message.direction == 'inbound' and message.body
        ).sorted('date')[-1:]
        values = {
            '{cliente}': channel.partner_id.name or channel.display_name or '',
            '{empresa}': channel.company_id.name or '',
            '{agente}': self.env.user.name or '',
            '{linea}': channel.whatsapp_number_id.name or '',
            '{ultimo_mensaje}': last_inbound.body or '',
            '{borrador}': draft_text or '',
        }
        text = self.instruction or ''
        for key, value in values.items():
            text = text.replace(key, value)
        rules = []
        if self.tone in TONE_INSTRUCTIONS:
            rules.append(TONE_INSTRUCTIONS[self.tone])
        rules.append(LANGUAGE_INSTRUCTIONS.get(self.language, LANGUAGE_INSTRUCTIONS['auto']))
        if self.max_words:
            rules.append('No superes las %s palabras.' % self.max_words)
        if self.output_mode in ('reply', 'rewrite'):
            rules.append(
                'Devuelve solo el texto final para el cliente, sin comillas, sin '
                'explicaciones y sin inventar precios, stock, fechas ni condiciones.')
        return '%s\n\n%s' % (text.strip(), ' '.join(rules))

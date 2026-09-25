# -*- coding: utf-8 -*-
import re
from datetime import timedelta

from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.chatroom_ai_learning.models.autonomy_level import learning_param
from odoo.addons.chatroom_ai_learning.models.learning_utils import normalize

TONES = [
    ('cercano', 'Cercano y amable'),
    ('formal', 'Formal'),
    ('neutro', 'Neutro y directo'),
]
TONE_TEXT = {
    'cercano': 'cercano y amable, tutea al cliente, frases simples',
    'formal': 'formal y respetuoso, trata al cliente de usted',
    'neutro': 'neutro, claro y directo, sin rodeos',
}
KNOWLEDGE_MODES = [
    ('strict', 'Solo con la información cargada'),
    ('guided', 'Prioriza la información cargada y orienta en general'),
]
DEFAULT_OBJECTIVE = (
    'Resolver las dudas de los clientes con la información oficial de la empresa, '
    'reunir los datos necesarios para atender su solicitud y dejarla lista para el equipo.')
DEFAULT_INSTRUCTIONS = """- Saluda por el nombre si lo conoces y ve al grano.
- Escribe mensajes cortos (2 a 4 frases), como en WhatsApp.
- Haz como máximo una o dos preguntas por mensaje.
- Si el cliente quiere comprar, contratar o cotizar, reúne los datos del guion que corresponda.
- Termina proponiendo el siguiente paso."""
DEFAULT_RESTRICTIONS = """- No inventes precios, descuentos, plazos, disponibilidad ni condiciones: usa solo la información entregada.
- No prometas nada que no esté en la información (entregas, aprobaciones, devoluciones).
- No digas que una cotización, pedido, reserva o pago está listo o confirmado: eso lo hace el equipo.
- No pidas contraseñas, códigos de verificación ni números completos de tarjeta.
- No hables de la competencia ni de temas ajenos al negocio.
- Si no sabes algo, dilo con naturalidad y ofrece consultarlo con el equipo."""
DEFAULT_SYNONYMS = """precio: costo, valor, cuánto cuesta, tarifa
envío: despacho, entrega, delivery, domicilio
horario: hora, atienden, abren, cierran
pago: pagar, transferencia, tarjeta, efectivo
devolución: cambio, reembolso, garantía"""
GREETING_RE = r'(hola|alo|buenas|buen dia|buenos dias|buenas tardes|buenas noches|hello|hi|saludos)'
THANKS_RE = r'(gracias|muchas gracias|mil gracias|ok gracias|gracias por la atencion|listo gracias)'


class ChatroomAiAgentProfile(models.Model):
    """Quién es el agente, qué debe lograr y cómo usa el conocimiento."""
    _name = 'chatroom.ai.agent.profile'
    _inherit = ['mail.thread']
    _description = 'Perfil del agente IA'
    _order = 'sequence, id'

    name = fields.Char(string='Perfil', required=True, tracking=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one('res.company', string='Empresa', default=lambda self: self.env.company,
                                 index=True)
    line_ids = fields.Many2many(
        'chatroom.whatsapp.number', string='Líneas',
        help='Vacío: atiende todas las líneas que no tengan un perfil propio.')

    # Identidad
    agent_name = fields.Char(string='Nombre del agente', default='Asistente virtual', required=True,
                             tracking=True)
    role = fields.Char(string='Rol', default='asesor de atención al cliente', required=True)
    business_description = fields.Text(
        string='Qué hace la empresa', tracking=True,
        help='A qué se dedica, qué ofrece, a quién atiende y cómo trabaja. La IA se presenta con esto.')
    objective = fields.Text(string='Objetivo del agente', default=DEFAULT_OBJECTIVE, required=True)
    tone = fields.Selection(TONES, string='Tono', default='cercano', required=True)
    style_notes = fields.Text(string='Estilo adicional',
                              help='Frases o formas de hablar de la marca, palabras a evitar, etc.')
    use_emojis = fields.Boolean(string='Usar emojis con moderación')

    # Instrucciones
    instructions = fields.Text(string='Qué debe hacer', default=DEFAULT_INSTRUCTIONS, required=True)
    restrictions = fields.Text(string='Qué no debe hacer nunca', default=DEFAULT_RESTRICTIONS, required=True)
    knowledge_mode = fields.Selection(KNOWLEDGE_MODES, string='Uso del conocimiento', default='strict',
                                      required=True)
    playbook_ids = fields.One2many('chatroom.ai.agent.playbook', 'profile_id', string='Guiones',
                                   context={'active_test': False})

    # Respuestas rápidas (sin IA ni tokens)
    greeting_message = fields.Char(
        string='Saludo', default='Hola {nombre}, soy {agente} de {empresa}. ¿En qué te puedo ayudar?',
        help='Se responde sin IA cuando el cliente solo saluda. Variables: {nombre}, {agente}, {empresa}.')
    thanks_message = fields.Char(
        string='Respuesta a un agradecimiento', default='Con gusto. Aquí estamos para lo que necesites.')

    # Autonomía desde el inicio
    bootstrap_autonomy = fields.Boolean(
        string='Responder solo desde el inicio lo respaldado por el conocimiento', default=True,
        help='Mientras un tipo de conversación está supervisado, la IA igual envía sola las respuestas '
             'basadas en la información publicada (o que solo piden datos del guion). Lo demás queda '
             'para aprobación. Nunca aplica a tipos bloqueados ni con la autonomía congelada.')
    bootstrap_min_confidence = fields.Float(string='Confianza mínima para responder solo', default=0.85)
    verify_before_send = fields.Boolean(
        string='Verificar antes de responder solo', default=True,
        help='Antes de enviar sola una respuesta, una segunda consulta breve comprueba que cada '
             'afirmación esté escrita en la información oficial. Evita respuestas deducidas o inventadas.')
    cost_mode = fields.Selection([
        ('quality', 'Máxima calidad'),
        ('balanced', 'Equilibrado (recomendado)'),
        ('economy', 'Ahorro'),
    ], string='Uso de IA', default='balanced', required=True,
        help='Máxima calidad: verifica todas las respuestas antes de enviarlas solas y no reutiliza respuestas. '
             'Equilibrado: no verifica lo que está copiado casi textual de la información y reutiliza la '
             'respuesta a una misma primera pregunta. Ahorro: verifica aún menos y reutiliza más.')
    cache_days = fields.Integer(string='Reutilizar respuestas por (días)', default=7)
    voice_replies = fields.Selection([
        ('never', 'Nunca, siempre texto'),
        ('audio', 'Con audio cuando el cliente manda un audio'),
        ('always', 'Siempre con audio'),
    ], string='Responder con voz', default='never', required=True,
        help='La respuesta se envía como nota de voz (el texto queda visible para el equipo). '
             'Usa la voz del proveedor de IA; si falla, se envía el texto.')
    voice_name = fields.Selection([
        ('nova', 'Nova (femenina, cálida)'), ('shimmer', 'Shimmer (femenina, clara)'),
        ('alloy', 'Alloy (neutra)'), ('echo', 'Echo (masculina)'), ('onyx', 'Onyx (masculina, grave)'),
        ('fable', 'Fable (narrativa)'),
    ], string='Voz', default='nova', required=True)
    catalog_in_prompt = fields.Boolean(
        string='Incluir el catálogo resumido', default=True,
        help='Si la empresa tiene hasta 30 productos a la venta, la IA recibe la lista con precios para '
             'poder recomendar aunque el cliente no diga el nombre exacto.')

    # Búsqueda en el conocimiento
    synonyms = fields.Text(
        string='Sinónimos del negocio', default=DEFAULT_SYNONYMS,
        help='Una línea por grupo: «precio: costo, valor». Así la IA encuentra la información aunque el '
             'cliente use otras palabras.')
    semantic_search = fields.Boolean(
        string='Búsqueda por significado', default=True,
        help='Además de las palabras, busca por significado con el proveedor de IA (embeddings). Si el '
             'proveedor no lo ofrece, sigue buscando por palabras.')

    # Seguimiento
    followup_hours = fields.Integer(
        string='Recordar un guion a medias después de (horas)', default=4,
        help='Si el cliente deja de responder a mitad de un guion, se le escribe una vez dentro de la '
             'ventana de 24 horas de WhatsApp. 0 = no recordar.')
    followup_message = fields.Char(
        string='Mensaje de seguimiento',
        default='¡Hola{coma_nombre}! ¿Seguimos con tu {guion}? Solo me falta: {faltan}.',
        help='Variables: {nombre}, {coma_nombre}, {guion}, {faltan}, {agente}, {empresa}.')

    gap_count = fields.Integer(compute='_compute_gap_count', string='Vacíos abiertos')
    dashboard_html = fields.Html(string='Tablero', compute='_compute_dashboard', sanitize=False)
    prompt_preview = fields.Text(string='Instrucciones completas', compute='_compute_prompt_preview')
    readiness_html = fields.Html(string='Preparación', compute='_compute_readiness', sanitize=False)
    is_ready = fields.Boolean(compute='_compute_readiness')
    auto_reply_on = fields.Boolean(compute='_compute_readiness')

    @api.constrains('bootstrap_min_confidence')
    def _check_confidence(self):
        for profile in self:
            if not 0.5 <= profile.bootstrap_min_confidence <= 1.0:
                raise UserError(_('La confianza mínima debe estar entre 0,50 y 1,00.'))

    # ------------------------------------------------------------------
    # Resolución
    # ------------------------------------------------------------------
    @api.model
    def _for_line(self, line=None, company=None):
        """Perfil que atiende una línea: el propio de la línea o el general."""
        forced = self.env.context.get('chatroom_ai_profile_id')
        if forced:
            profile = self.sudo().browse(forced).exists()
            if profile:
                return profile
        company = company or self.env.company
        profiles = self.sudo().search(['|', ('company_id', '=', False), ('company_id', '=', company.id)])
        if line:
            own = profiles.filtered(lambda profile: line in profile.line_ids)[:1]
            if own:
                return own
        return profiles.filtered(lambda profile: not profile.line_ids)[:1]

    # ------------------------------------------------------------------
    # Instrucciones para la IA
    # ------------------------------------------------------------------
    def _company(self):
        return self.company_id or self.env.company

    def _identity_prompt(self, partner=None):
        """Quién es el agente y cómo trabaja. Va en todas las consultas de IA."""
        self.ensure_one()
        tone = TONE_TEXT.get(self.tone, '')
        if self.style_notes:
            tone += '. %s' % self.style_notes.strip()
        tone += '. %s' % (_('Puedes usar algún emoji con moderación') if self.use_emojis
                          else _('No uses emojis'))
        knowledge = {
            'strict': _('Responde únicamente con la información entregada en este mensaje (datos de la '
                        'empresa, productos, manuales, ejemplos y datos del cliente). Si algo no está, no '
                        'lo supongas.'),
            'guided': _('Prioriza la información entregada. Puedes orientar en términos generales, pero '
                        'nunca inventes datos concretos (precios, plazos, condiciones, disponibilidad).'),
        }[self.knowledge_mode]
        parts = [
            _('IDENTIDAD\nEres %(agent)s, %(role)s de %(company)s. Atiendes clientes por WhatsApp. '
              'Responde en el idioma en que escribe el cliente (por defecto, español).') % {'agent': self.agent_name, 'role': self.role, 'company': self._company().name},
        ]
        if self.business_description:
            parts.append(_('Sobre la empresa: %s') % self.business_description.strip())
        parts.append(_('Objetivo: %s') % self.objective.strip())
        parts.append(_('Tono: %s.') % tone)
        parts.append(_('QUÉ DEBES HACER\n%s') % self.instructions.strip())
        parts.append(_('LÍMITES (obligatorios)\n%s') % self.restrictions.strip())
        parts.append(_('USO DE LA INFORMACIÓN\n%s') % knowledge)
        return '\n'.join(parts)

    def _contract_prompt(self, playbook=None, data=None, done=False):
        """Formato de respuesta y guiones: lo que la guardia sabe leer."""
        self.ensure_one()
        lines = [_(
            'FORMATO DE RESPUESTA\n'
            'Responde SOLO con JSON válido, sin texto fuera del JSON:\n'
            '{"intent": "consulta|venta|soporte|queja|otro", "guion": "", "datos": {}, '
            '"reply": "mensaje para el cliente", "pregunta_dato": "", "respaldo": "conocimiento|guion|cortesia|ninguno", '
            '"vacio": "", "confidence": <número de 0 a 1>, "needs_human": false, "reason": "motivo breve", '
            '"sentiment": "positive|neutral|negative", "urgency": "low|normal|high|critical"}\n'
            'Complétalo en ese orden: primero el guion y los datos que ya dio el cliente; luego redacta '
            '"reply"; al final clasifica el respaldo y el vacío de ESA respuesta.\n'
            '- respaldo: "conocimiento" SOLO si cada dato, condición o respuesta de sí/no que das está '
            'escrito explícitamente en la información entregada. Si lo deduces, lo supones o lo '
            'completas con sentido común, NO es conocimiento: usa "ninguno". "guion" si solo pides '
            'datos del guion; "cortesia" si es un saludo o cierre sin datos.\n'
            '- vacio: si el cliente preguntó algo cuya respuesta NO está escrita en la información, '
            'escribe aquí su pregunta (ej.: "¿Pierdo la garantía si armo el escritorio yo mismo?"), '
            'dile que lo consultarás con el equipo, no respondas sí ni no, y marca needs_human=true.\n'
            '- Si la información publicada ayuda en el caso (políticas, plazos, costos), inclúyela junto '
            'con las preguntas que hagas.\n'
            '- needs_human=true solo si el cliente pide una persona, reclama, hay un tema de pagos o '
            'reembolsos, hay urgencia o no puedes avanzar sin el equipo. Pedir datos del guion NO '
            'requiere persona.\n'
            '- pregunta_dato: la clave del dato del guion que le pides al cliente en este mensaje (una sola; '
            '"" si no pides ninguno). Si ese dato tiene opciones, el cliente las verá como botones: no las '
            'enumeres en el texto.\n'
            '- confidence: qué tan seguro estás de que tu respuesta es correcta y adecuada (0 a 1). '
            'Pedir un dato del guion que falta, o saludar, es una respuesta correcta: confianza alta.\n'
            '- Idioma: escribe "reply" en el idioma del último mensaje del cliente. Si escribe en inglés '
            'u otro idioma, responde en ese idioma aunque la información esté en español.')]
        playbooks = self.playbook_ids.filtered('active')
        if playbooks:
            lines.append(_('GUIONES (datos a reunir según lo que necesita el cliente)'))
            lines.extend(item._prompt_block() for item in playbooks)
            example = playbooks[0].field_ids[:2]
            sample = ', '.join('"%s": "..."' % field.key for field in example)
            lines.append(_(
                '- guion: código del guion que aplica ("" si ninguno). datos: TODOS los datos del guion '
                'que el cliente dio, INCLUIDO su último mensaje, con esas claves y con sus palabras '
                '(formato: {%(sample)s}). Ej.: si escribe «quiero cotizar 2 sillas» y el guion pide '
                'producto y cantidad, anota ambos ya en esta respuesta. No incluyas los que no dio. Pide primero los '
                'obligatorios que falten, de a uno o dos, sin repetir los ya obtenidos; los opcionales '
                'solo si la conversación lo permite. Al tener los obligatorios, resume los datos y di que '
                'el equipo continuará (no digas que ya está listo).') % {'sample': sample})
        return '\n'.join(lines)

    def _dynamic_block(self, partner=None, playbook=None, data=None, done=False):
        """Lo propio de esta conversación. Va al final del prompt para que el
        comienzo (identidad, formato, guiones) sea idéntico entre
        conversaciones y el proveedor lo reutilice con descuento."""
        self.ensure_one()
        lines = []
        if partner and partner.name:
            lines.append(_('Cliente: %s.') % partner.name)
        if playbook:
            lines.append(playbook._state_block(data or {}, done))
        return _('DATOS DE ESTA CONVERSACIÓN\n%s') % '\n'.join(lines) if lines else ''

    def _verify_threshold(self):
        """Cobertura desde la cual una respuesta se considera copiada de la
        información y no necesita verificador (None = verificar siempre)."""
        self.ensure_one()
        return {'quality': None, 'balanced': 0.85, 'economy': 0.7}.get(self.cost_mode)

    def _wants_voice(self, channel):
        self.ensure_one()
        if self.voice_replies == 'always':
            return True
        if self.voice_replies != 'audio':
            return False
        last = (channel._ai_pending_inbound() or channel._ai_latest_inbound())[-1:]
        return bool(last) and last.message_type == 'audio'

    def _catalog_block(self):
        """Lista corta del catálogo (solo si es pequeño) para recomendar."""
        self.ensure_one()
        if not self.catalog_in_prompt or 'product.template' not in self.env:
            return ''
        company = self._company()
        domain = [('sale_ok', '=', True), ('active', '=', True),
                  '|', ('company_id', '=', False), ('company_id', '=', company.id)]
        Template = self.env['product.template'].sudo()
        if Template.search_count(domain) > 30:
            return ''
        currency = company.currency_id
        rows = ['- %s: %.2f %s' % (product.name, product.list_price, currency.symbol or currency.name or '')
                for product in Template.search(domain, order='name', limit=30)]
        return _('Catálogo (productos a la venta y precio de lista):\n%s') % '\n'.join(rows) if rows else ''

    # ------------------------------------------------------------------
    # Respuestas rápidas
    # ------------------------------------------------------------------
    def _render(self, template, partner_name=''):
        self.ensure_one()
        first = (partner_name or '').strip().split(' ')[0] if partner_name else ''
        text = (template or '').replace('{nombre}', first).replace('{agente}', self.agent_name or '') \
            .replace('{empresa}', self._company().name or '')
        text = re.sub(r'\s+([,.!?])', r'\1', text)
        return re.sub(r'\s{2,}', ' ', text).strip()

    def _followup_text(self, playbook, data, partner_name=''):
        self.ensure_one()
        first = (partner_name or '').strip().split(' ')[0] if partner_name else ''
        missing = ', '.join(playbook._missing(data).mapped('label')).lower() or _('confirmar los datos')
        text = (self.followup_message or '').replace('{coma_nombre}', ', %s' % first if first else '') \
            .replace('{guion}', playbook.name.lower()).replace('{faltan}', missing)
        return self._render(text, partner_name)

    def _local_reply(self, text, partner_name=''):
        """Saludo o agradecimiento sin IA; cualquier otra cosa va a la IA."""
        self.ensure_one()
        clean = re.sub(r'[^\w ]', '', normalize(text or '')).strip()
        if not clean:
            return False
        if self.greeting_message and re.fullmatch(GREETING_RE, clean):
            return self._render(self.greeting_message, partner_name)
        if self.thanks_message and re.fullmatch(THANKS_RE, clean):
            return self._render(self.thanks_message, partner_name)
        return False

    # ------------------------------------------------------------------
    # Pantalla
    # ------------------------------------------------------------------
    def _compute_gap_count(self):
        Gap = self.env['chatroom.ai.knowledge.gap']
        for profile in self:
            profile.gap_count = Gap.search_count([('profile_id', '=', profile.id),
                                                  ('state', 'in', ('open', 'proposed'))])

    @api.depends('agent_name', 'role', 'business_description', 'objective', 'tone', 'style_notes',
                 'use_emojis', 'instructions', 'restrictions', 'knowledge_mode', 'playbook_ids',
                 'playbook_ids.active', 'playbook_ids.field_ids')
    def _compute_prompt_preview(self):
        for profile in self:
            if not (profile.agent_name and profile.instructions and profile.restrictions and profile.objective):
                profile.prompt_preview = False
                continue
            profile.prompt_preview = '%s\n\n%s\n\n%s' % (
                profile._identity_prompt(), profile._contract_prompt(),
                _('(Aquí se agregan el conocimiento publicado que coincide con la pregunta, los '
                  'ejemplos aprobados por el equipo y la memoria del cliente.)'))

    def _dashboard_values(self, days=30):
        self.ensure_one()
        Event = self.env['chatroom.ai.agent.event'].sudo()
        since = fields.Datetime.now() - timedelta(days=days)
        domain = [('create_date', '>=', since), '|', ('profile_id', '=', self.id), ('profile_id', '=', False)]
        counts = {kind: 0 for kind in ('sent', 'local', 'approval', 'review', 'handoff', 'followup', 'skipped', 'error')}
        for kind, count in Event._read_group(domain, ['kind'], ['__count']):
            counts[kind] = count
        answered = counts['sent'] + counts['local'] + counts['approval'] + counts['review'] + counts['handoff']
        alone = counts['sent'] + counts['local']
        [(latency,)] = Event._read_group(domain + [('kind', '=', 'sent'), ('latency_ms', '>', 0)],
                                         [], ['latency_ms:avg'])
        [(cost, tokens)] = Event._read_group(domain, [], ['cost:sum', 'tokens:sum'])
        reused = Event.search_count(domain + [('cached', '=', True)])
        reasons = Event._read_group(domain + [('kind', '=', 'handoff')], ['reason'], ['__count'],
                                    order='__count desc', limit=3)
        savings = self._savings(domain, since, reused)
        return {
            'savings': savings,
            'trend': self._weekly_trend(),
            'counts': counts, 'answered': answered,
            'alone_rate': 100.0 * alone / answered if answered else 0.0,
            'latency': (latency or 0) / 1000.0,
            'cost': cost or 0.0,
            'tokens': tokens or 0,
            'reused': reused,
            'reasons': [(reason or _('sin motivo'), count) for reason, count in reasons],
            'gaps': self.gap_count,
        }

    def _savings(self, domain, since, reused):
        """Ahorro estimado: respuestas reutilizadas y entrada cobrada a mitad de precio."""
        self.ensure_one()
        Event = self.env['chatroom.ai.agent.event'].sudo()
        paid = Event.search(domain + [('kind', '=', 'sent'), ('cached', '=', False), ('tokens', '>', 0)], limit=200)
        avg_cost = sum(paid.mapped('cost')) / len(paid) if paid else 0.0
        avg_tokens = sum(paid.mapped('tokens')) / len(paid) if paid else 0.0
        cached_tokens, cached_usd = 0, 0.0
        if 'chatroom.ai.usage.event' in self.env:
            Usage = self.env['chatroom.ai.usage.event'].sudo()
            Pricing = self.env['chatroom.ai.provider.model'].sudo()
            try:
                discount = float(self.env['ir.config_parameter'].sudo().get_param(
                    'chatroom_ai_usage.cached_input_discount', '0.5'))
            except (TypeError, ValueError):
                discount = 0.5
            for model, tokens in Usage._read_group([('request_date', '>=', since), ('cached_tokens', '>', 0)],
                                                   ['model'], ['cached_tokens:sum']):
                cached_tokens += tokens or 0
                input_rate = Pricing._pricing_for_model(model)[0] if model else 0.0
                cached_usd += (tokens or 0) * input_rate * discount / 1000000.0
        return {'reused_usd': reused * avg_cost, 'reused_tokens': int(reused * avg_tokens),
                'cached_tokens': cached_tokens, 'cached_usd': cached_usd,
                'usd': reused * avg_cost + cached_usd}

    def _weekly_trend(self, weeks=8):
        """Por semana: conversaciones atendidas y % que respondió sola."""
        self.ensure_one()
        Event = self.env['chatroom.ai.agent.event'].sudo()
        today = fields.Date.context_today(self)
        start = today - timedelta(days=today.weekday() + 7 * (weeks - 1))
        rows = {}
        domain = [('date', '>=', start), ('kind', 'in', ('sent', 'local', 'approval', 'review', 'handoff')),
                  '|', ('profile_id', '=', self.id), ('profile_id', '=', False)]
        for day, kind, count in Event._read_group(domain, ['date:day', 'kind'], ['__count']):
            day = fields.Date.to_date(day)
            week = day - timedelta(days=day.weekday())
            total, alone = rows.get(week, (0, 0))
            rows[week] = (total + count, alone + (count if kind in ('sent', 'local') else 0))
        trend = []
        for index in range(weeks):
            week = start + timedelta(days=7 * index)
            total, alone = rows.get(week, (0, 0))
            trend.append({'week': week, 'total': total, 'rate': 100.0 * alone / total if total else 0.0})
        return trend

    def _compute_dashboard(self):
        for profile in self:
            if not profile.id:
                profile.dashboard_html = False
                continue
            values = profile._dashboard_values()
            counts = values['counts']
            tiles = [
                (_('Respondió sola'), '%.0f%%' % values['alone_rate'], 'text-success'),
                (_('Conversaciones atendidas'), values['answered'], ''),
                (_('Para aprobar'), counts['approval'] + counts['review'], 'text-info'),
                (_('Pasó a una persona'), counts['handoff'], 'text-warning'),
                (_('Reutilizadas (sin IA)'), values['reused'], 'text-success' if values['reused'] else ''),
                (_('Respuesta promedio'), '%.1f s' % values['latency'], ''),
                (_('Costo IA'), '%.4f USD' % values['cost'] if values['cost'] else _('%s tokens (sin precio cargado)')
                 % values['tokens'], ''),
                (_('Vacíos por resolver'), values['gaps'], 'text-danger' if values['gaps'] else ''),
            ]
            cards = Markup('').join(
                Markup('<div class="col-6 col-md-3 mb-2"><div class="border rounded p-2 h-100">'
                       '<div class="small text-muted">%s</div><div class="fs-4 fw-bold %s">%s</div></div></div>') % (
                    label, css, value) for label, value, css in tiles)
            reasons = Markup('').join(Markup('<li>%s — %s</li>') % (reason, count)
                                      for reason, count in values['reasons'])
            savings = values['savings']
            saving_text = (_('%.4f USD') % savings['usd']) if savings['usd'] else _('%s tokens') % (
                savings['reused_tokens'] + savings['cached_tokens'] // 2)
            saving_detail = _('%(reused)s respuestas reutilizadas sin IA y %(cached)s tokens de entrada a mitad '
                              'de precio.') % {'reused': values['reused'], 'cached': savings['cached_tokens']}
            bars = Markup('').join(
                Markup('<div class="d-flex flex-column align-items-center flex-fill" title="%s">'
                       '<div class="small fw-bold">%s</div>'
                       '<div class="w-75 bg-body-secondary rounded-top d-flex align-items-end" style="height:70px">'
                       '<div class="w-100 bg-success rounded-top" style="height:%s%%"></div></div>'
                       '<div class="small text-muted">%s</div></div>') % (
                    _('%(total)s atendidas, %(rate).0f%% sola') % {'total': week['total'], 'rate': week['rate']},
                    '%.0f%%' % week['rate'] if week['total'] else '—', int(week['rate']),
                    week['week'].strftime('%d/%m'))
                for week in values['trend'])
            trend = Markup('<div class="mt-3"><b>%s</b><div class="d-flex gap-1 mt-1 o_agent_trend">%s</div></div>') % (
                _('Respondió sola por semana'), bars)
            saving = Markup('<div class="alert alert-success py-2 mt-3 mb-0"><b>%s: %s</b> — %s</div>') % (
                _('Ahorro estimado'), saving_text, saving_detail)
            profile.dashboard_html = Markup(
                '<div class="row g-2">%s</div><div class="small text-muted mt-2">%s</div>%s%s%s') % (
                cards, _('Últimos 30 días.'), saving, trend,
                Markup('<div class="mt-2"><b>%s</b><ul class="mb-0">%s</ul></div>') % (
                    _('Motivos de traspaso más frecuentes'), reasons) if reasons else Markup(''))

    def action_open_setup(self):
        self.ensure_one()
        wizard = self.env['chatroom.ai.agent.setup'].create({'profile_id': self.id})
        return wizard._reopen()

    def action_preview_voice(self):
        """Escuchar la voz elegida con el saludo del perfil antes de activarla."""
        self.ensure_one()
        text = self._render(self.greeting_message or '', '') or _('Hola, ¿en qué te puedo ayudar?')
        audio = self.env['chatroom.channel']._ai_speech(text, self)
        if not audio:
            raise UserError(_('Configura el proveedor de IA para escuchar la voz.'))
        Attachment = self.env['ir.attachment'].sudo()
        Attachment.search([('res_model', '=', self._name), ('res_id', '=', self.id),
                           ('name', '=like', 'voz-%')]).unlink()
        attachment = Attachment.create({'name': 'voz-%s.ogg' % self.voice_name, 'raw': audio,
                                        'mimetype': 'audio/ogg', 'res_model': self._name, 'res_id': self.id})
        return {'type': 'ir.actions.act_url', 'target': 'new',
                'url': '/web/content/%s?download=false' % attachment.id}

    def action_view_events(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('chatroom_ai_agent_profile.action_agent_event')
        action['domain'] = ['|', ('profile_id', '=', self.id), ('profile_id', '=', False)]
        return action

    def action_embed_knowledge(self):
        count = self.env['ai.knowledge.base'].sudo()._cron_embed_missing(limit=500)
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'title': _('Búsqueda por significado'), 'type': 'success' if count else 'info', 'sticky': False,
            'message': _('%s fragmentos actualizados.') % count if count else _(
                'No hubo fragmentos nuevos, o el proveedor no ofrece búsqueda por significado.')}}

    def _readiness_checks(self):
        self.ensure_one()
        env = self.env
        icp = env['ir.config_parameter'].sudo()
        company = self._company()
        knowledge = env['ai.knowledge.base'].sudo().search_count([
            ('active', '=', True), ('state', '=', 'indexed'), ('publication_state', '=', 'published'),
            '|', ('company_id', '=', False), ('company_id', '=', company.id)])
        try:
            provider = bool(env['chatroom.channel']._ai_get_credentials())
        except Exception:  # noqa: BLE001 - solo informativo
            provider = False

        def enabled(key, default=False):
            value = icp.get_param(key)
            if value in (False, None, ''):
                return default
            return str(value).strip().lower() in ('1', 'true', 'yes', 'on')

        auto = enabled('chatroom_whatsapp.ai_auto_reply') and enabled('chatroom_ai_agent.safe_auto_reply', True)
        frozen = learning_param(env, 'autonomy_frozen', False)
        last_run = env['chatroom.ai.eval.run'].sudo().search([], limit=1)
        playbooks = len(self.playbook_ids.filtered('active'))
        return [
            ('description', len((self.business_description or '').strip()) >= 40,
             _('Descripción de la empresa'),
             _('Completa «Qué hace la empresa»: la IA se presenta y responde con eso.')),
            ('knowledge', knowledge > 0, _('Conocimiento publicado (%s)') % knowledge,
             _('Carga y publica al menos un documento o texto en Base de conocimiento.')),
            ('playbooks', playbooks > 0, _('Guiones activos (%s)') % playbooks,
             _('Opcional: define qué datos pedir según lo que necesita el cliente.')),
            ('provider', provider, _('Proveedor de IA configurado'),
             _('Configura el proveedor y la clave en Ajustes de Chatroom WhatsApp.')),
            ('tests', bool(last_run) and not frozen,
             _('Pruebas de la IA: %s') % (last_run.summary if last_run else _('sin ejecutar')),
             _('Ejecuta las pruebas (y prueba el agente) antes de dejarlo responder solo.')),
            ('auto', auto, _('Respuesta automática activada'),
             _('Pulsa «Activar respuesta automática» cuando todo lo anterior esté listo.')),
        ]

    @api.depends('business_description', 'playbook_ids.active')
    def _compute_readiness(self):
        for profile in self:
            if not profile.id:
                profile.readiness_html = False
                profile.is_ready = profile.auto_reply_on = False
                continue
            checks = profile._readiness_checks()
            profile.auto_reply_on = next(ok for key, ok, _label, _help in checks if key == 'auto')
            required = {'description', 'knowledge', 'provider', 'auto'}
            profile.is_ready = all(ok for key, ok, _label, _help in checks if key in required)
            rows = Markup('').join(
                Markup('<li class="%s"><i class="fa %s me-2"/><b>%s</b>%s</li>') % (
                    'text-success' if ok else 'text-warning',
                    'fa-check-circle' if ok else 'fa-exclamation-circle',
                    label, Markup('') if ok else Markup(' — <span class="text-muted">%s</span>') % hint)
                for _key, ok, label, hint in checks)
            title = _('Listo para atender solo') if profile.is_ready else _('Pendiente para atender solo')
            profile.readiness_html = Markup('<div><h5>%s</h5><ul class="list-unstyled mb-0">%s</ul></div>') % (
                title, rows)

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------
    def action_open_simulator(self):
        self.ensure_one()
        simulator = self.env['chatroom.ai.agent.simulator'].create({'profile_id': self.id})
        return simulator._reopen()

    def action_enable_auto_reply(self):
        self.ensure_one()
        if not self.env['chatroom.channel']._ai_get_credentials():
            raise UserError(_('Primero configura el proveedor de IA en Ajustes de Chatroom WhatsApp.'))
        icp = self.env['ir.config_parameter'].sudo()
        for key in ('chatroom_whatsapp.ai_auto_reply', 'chatroom_ai_agent.safe_auto_reply',
                    'chatroom_ai_learning.graduated_autonomy', 'chatroom_ai_learning.handoff_enabled'):
            icp.set_param(key, 'True')
        self.message_post(body=_('Respuesta automática activada por %s.') % self.env.user.name)
        return True

    def action_disable_auto_reply(self):
        self.env['ir.config_parameter'].sudo().set_param('chatroom_whatsapp.ai_auto_reply', 'False')
        for profile in self:
            profile.message_post(body=_('Respuesta automática desactivada por %s.') % self.env.user.name)
        return True

    def action_run_tests(self):
        return self.env['chatroom.ai.eval.run'].action_run_from_menu()

    def action_view_gaps(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('chatroom_ai_agent_profile.action_knowledge_gap')
        action['domain'] = [('profile_id', '=', self.id)]
        return action

    @staticmethod
    def _escape(value):
        return escape(value or '')

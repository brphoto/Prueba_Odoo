import re
import unicodedata
from datetime import datetime, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .marketing_social_constants import PLATFORM_LABELS


class MarketingSocialAgentChat(models.Model):
    _name = 'marketing.social.agent.chat'
    _description = 'Agente analítico de marketing social'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'write_date desc, id desc'

    name = fields.Char(string='Consulta', required=True, default='Nueva consulta de marketing')
    draft_message = fields.Text(string='Pregunta', help='Escribe la consulta en lenguaje natural.')
    answer = fields.Text(string='Respuesta', readonly=True)
    state = fields.Selection([
        ('draft', 'Borrador'), ('answered', 'Respondida'), ('error', 'Error'),
    ], string='Estado', default='draft', required=True)
    platform_filter = fields.Selection(
        [('all', 'Todas las redes')] + list(PLATFORM_LABELS.items()),
        string='Red a analizar', default='all', required=True)
    period_days = fields.Integer(string='Período (días)', default=30, required=True)
    intent = fields.Selection([
        ('summary', 'Resumen'), ('top', 'Mejor contenido'),
        ('engagement', 'Engagement'), ('trend', 'Tendencia'),
        ('comments', 'Comentarios'), ('audience', 'Audiencia'),
        ('inbox', 'Bandeja social'), ('quality', 'Calidad de datos'),
    ], string='Consulta interpretada', readonly=True)
    chat_message_ids = fields.One2many(
        'marketing.social.agent.message', 'chat_id', string='Conversación', readonly=True)
    source_publication_ids = fields.Many2many(
        'marketing.social.publication', string='Publicaciones fuente', readonly=True)
    source_summary = fields.Text(
        string='Fuentes consultadas', readonly=True,
        help='Publicaciones y métricas utilizadas para construir la respuesta.')
    message_count = fields.Integer(compute='_compute_message_count', string='Mensajes')
    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True,
        default=lambda self: self.env.company, index=True)

    @api.depends('chat_message_ids')
    def _compute_message_count(self):
        for record in self:
            record.message_count = len(record.chat_message_ids)

    def _normalize(self, text):
        value = unicodedata.normalize('NFKD', text or '')
        value = ''.join(char for char in value if not unicodedata.combining(char))
        return re.sub(r'\s+', ' ', value.lower()).strip()

    def _date_range(self):
        date_to = fields.Date.context_today(self)
        date_from = date_to - timedelta(days=max(self.period_days or 30, 1) - 1)
        return date_from, date_to

    def _rows(self):
        date_from, date_to = self._date_range()
        domain = [
            ('company_id', '=', self.company_id.id),
            ('published_at', '>=', datetime.combine(date_from, datetime.min.time())),
            ('published_at', '<=', datetime.combine(date_to, datetime.max.time())),
            ('active', '=', True),
        ]
        if self.platform_filter != 'all':
            domain.append(('platform', '=', self.platform_filter))
        publications = self.env['marketing.social.publication'].search(domain)
        return self.env['marketing.social.metric.snapshot']._latest_per_publication(
            publications, date_from, date_to)

    def _number(self, value):
        return '{:,.0f}'.format(value or 0).replace(',', '.')

    def _percent(self, value):
        return ('%.2f' % (value or 0)).replace('.', ',')

    def _platform_text(self):
        return 'todas las redes' if self.platform_filter == 'all' else PLATFORM_LABELS.get(self.platform_filter, self.platform_filter)

    def _social_accounts(self):
        domain = [
            ('company_id', '=', self.company_id.id), ('active', '=', True),
        ]
        if self.platform_filter != 'all':
            domain.append(('platform', '=', self.platform_filter))
        return self.env['marketing.social.account'].search(domain)

    def _answer_inbox_question(self, question):
        normalized = self._normalize(question)
        if not any(word in normalized for word in (
                'bandeja', 'inbox', 'conversacion', 'conversaciones', 'mensaje',
                'mensajes', 'chat', 'chats')):
            return False
        accounts = self._social_accounts()
        Conversation = self.env['marketing.social.conversation']
        Message = self.env['marketing.social.conversation.message']
        conversations = Conversation.search([('account_id', 'in', accounts.ids)])
        messages = Message.search([('account_id', 'in', accounts.ids)])
        open_count = len(conversations.filtered(lambda item: item.state == 'open'))
        unread = len(messages.filtered(
            lambda item: item.direction == 'inbound' and item.read_state == 'unread'))
        self.intent = 'inbox'
        if not accounts:
            return _('No hay cuentas sociales activas para consultar la bandeja. Conecta Meta o importa una cuenta primero.')
        return _(
            'Bandeja social de %s: %s conversación(es), %s abierta(s), %s mensaje(s) y %s entrante(s) sin leer. '
            'La sincronización de conversaciones es independiente de las publicaciones: una página puede tener mensajes aunque no entregue posts o Insights.'
        ) % (
            self._platform_text(), self._number(len(conversations)), self._number(open_count),
            self._number(len(messages)), self._number(unread),
        )

    def _answer_quality_question(self, question):
        normalized = self._normalize(question)
        if not any(word in normalized for word in (
                'calidad', 'real', 'calculable', 'disponible', 'insights',
                'medida', 'medicion', 'cero', 'por que', 'porque')):
            return False
        date_from, date_to = self._date_range()
        domain = [
            ('company_id', '=', self.company_id.id),
            ('snapshot_date', '>=', date_from), ('snapshot_date', '<=', date_to),
        ]
        if self.platform_filter != 'all':
            domain.append(('platform', '=', self.platform_filter))
        metrics = self.env['marketing.social.metric.snapshot'].search(domain)
        counts = {
            status: len(metrics.filtered(lambda metric, status=status: metric.metric_status == status))
            for status in ('verified', 'partial', 'unavailable', 'demo')
        }
        self.intent = 'quality'
        if not metrics:
            return _('No hay instantáneas de métricas en el período. El engagement todavía no se puede calcular.')
        measured = counts['verified'] + counts['partial'] + counts['demo']
        if not measured:
            return _(
                'El engagement aparece en 0,00%% porque no existen métricas utilizables: %s publicación(es) están sin datos del proveedor. '
                'Esto significa «no calculable», no necesariamente cero interacción. Revisa permisos de Insights y sincroniza nuevamente Meta.'
            ) % self._number(counts['unavailable'])
        return _(
            'Calidad de métricas en %s: %s verificadas, %s parciales, %s demo y %s no disponibles. '
            'El engagement se calcula solo con %s registro(s) medible(s); las métricas no disponibles se excluyen para no convertir un vacío en un falso cero.'
        ) % (
            self._platform_text(), self._number(counts['verified']), self._number(counts['partial']),
            self._number(counts['demo']), self._number(counts['unavailable']), self._number(measured),
        )

    def _vehicle_rows(self):
        """Read the optional external catalog without making it a hard dependency."""
        if 'marketing.vehicle.listing' not in self.env:
            # El `return self.env['marketing.vehicle.listing']` que habia
            # aqui anulaba la propia comprobacion: acceder al modelo que
            # se acaba de descartar lanza KeyError. Sin el modulo opcional
            # de Patiotuerca instalado, preguntarle al agente por
            # vehiculos (o por cualquier cosa, porque esto corre en cada
            # consulta) reventaba con un error de servidor.
            return None
        return self.env['marketing.vehicle.listing'].sudo().search([
            ('company_id', '=', self.company_id.id), ('active', '=', True),
        ], order='status, price, name', limit=100)

    def _answer_vehicle_question(self, question, vehicles):
        normalized = self._normalize(question)
        if not any(word in normalized for word in (
                'vehiculo', 'vehiculos', 'auto', 'autos', 'carro', 'carros',
                'patiotuerca', 'catalogo', 'publicado', 'despublicado',
                'reservado', 'vendido')):
            return False
        status_labels = {
            'published': 'publicado', 'unpublished': 'despublicado',
            'paused': 'pausado', 'reserved': 'reservado', 'sold': 'vendido',
        }
        requested_status = next((status for status, words in {
            'published': ('publicado', 'publicados', 'online', 'activos'),
            'unpublished': ('despublicado', 'despublicizados', 'inactivos'),
            'reserved': ('reservado', 'reservados'),
            'sold': ('vendido', 'vendidos'),
        }.items() if any(word in normalized for word in words)), False)
        # El `if not vehicles` va ANTES de filtrar: sin catalogo instalado
        # `vehicles` es None y no tiene `.filtered`.
        if not vehicles:
            self.intent = 'audience'
            return _('No hay vehículos activos en el catálogo externo. Sincroniza Patiotuerca o carga el demo para consultar anuncios.')
        selected = vehicles.filtered(
            lambda vehicle: vehicle.status == requested_status) if requested_status else vehicles
        self.intent = 'audience'
        counts = {
            status: len(vehicles.filtered(lambda vehicle, status=status: vehicle.status == status))
            for status in ('published', 'unpublished', 'paused', 'reserved', 'sold')
        }
        summary = ', '.join('%s %s' % (count, label) for label, count in (
            ('publicados', counts['published']), ('despublicados', counts['unpublished']),
            ('pausados', counts['paused']), ('reservados', counts['reserved']),
            ('vendidos', counts['sold']),
        ) if count)
        if not selected:
            return _('No encontré vehículos %s. El catálogo tiene %s.') % (
                status_labels.get(requested_status, requested_status), summary)
        lines = []
        for vehicle in selected[:8]:
            price = ('%.2f %s' % (vehicle.price, vehicle.currency or 'USD')).replace('.', ',')
            details = ' · '.join(filter(None, [vehicle.brand, vehicle.model, vehicle.version]))
            lines.append('• %s — %s — %s%s' % (
                vehicle.name, details or 'sin detalle', price,
                (' — %s' % vehicle.url) if vehicle.url else ''))
        qualifier = ' %s' % status_labels[requested_status] if requested_status else ''
        return _('Catálogo Patiotuerca: %s. Mostrando%s %s anuncio(s):\n%s') % (
            summary, qualifier, len(selected), '\n'.join(lines))

    def _answer_question(self, question):
        normalized = self._normalize(question)
        # Las tres ramas de abajo no usan ni las metricas ni el catalogo:
        # calcularlos antes de saber si hacen falta significaba, en cada
        # pregunta sobre la bandeja o la calidad del dato, recorrer todas
        # las publicaciones del periodo para tirar el resultado.
        vehicle_answer = self._answer_vehicle_question(question, self._vehicle_rows())
        if vehicle_answer:
            self.source_publication_ids = [(6, 0, [])]
            return vehicle_answer
        inbox_answer = self._answer_inbox_question(question)
        if inbox_answer:
            self.source_publication_ids = [(6, 0, [])]
            return inbox_answer
        quality_answer = self._answer_quality_question(question)
        if quality_answer:
            self.source_publication_ids = [(6, 0, [])]
            return quality_answer
        rows = self._rows()
        self.source_publication_ids = [(6, 0, [publication.id for publication, _metric in rows])]
        if not rows:
            self.intent = 'summary'
            return _('No hay datos de publicaciones para %s en los últimos %s días. Sincroniza cuentas o carga el modo demo para comenzar.') % (self._platform_text(), self.period_days)
        if any(word in normalized for word in ('mejor', 'top', 'exitos', 'destac')):
            self.intent = 'top'
            best = max(rows, key=lambda item: item[1].engagement_rate)
            metric = best[1]
            return _(
                'La publicación con mejor engagement es «%s» en %s: %.2f%%. '
                'Alcance: %s; interacciones: %s; reproducciones: %s; oportunidades atribuidas: %s. '
                'Conviene replicar su tema, formato y horario.'
            ) % (
                best[0].name, PLATFORM_LABELS.get(best[0].platform, best[0].platform),
                metric.engagement_rate, self._number(metric.reach),
                self._number(metric.total_interactions), self._number(metric.views),
                self._number(metric.leads),
            )
        if any(word in normalized for word in ('tendencia', 'tendencias', 'crecimiento', 'evolucion', 'compar')):
            self.intent = 'trend'
            total_reach = sum(metric.reach for _publication, metric in rows)
            total_interactions = sum(metric.total_interactions for _publication, metric in rows)
            ranked_platforms = {}
            for _publication, metric in rows:
                ranked_platforms.setdefault(_publication.platform, [0, 0])
                ranked_platforms[_publication.platform][0] += metric.reach
                ranked_platforms[_publication.platform][1] += metric.total_interactions
            best_platform = max(ranked_platforms, key=lambda key: ranked_platforms[key][1] / (ranked_platforms[key][0] or 1))
            return _(
                'La tendencia del período muestra %s publicaciones, %s de alcance y %s interacciones. '
                'La red con mejor relación de interacción sobre alcance es %s. '
                'El engagement consolidado es %.2f%%. Para decidir la siguiente campaña, replica los formatos de mayor rendimiento y prueba una variación del tema.'
            ) % (
                self._number(len(rows)), self._number(total_reach), self._number(total_interactions),
                PLATFORM_LABELS.get(best_platform, best_platform),
                total_interactions / total_reach * 100 if total_reach else 0.0,
            )
        if any(word in normalized for word in ('comentario', 'comentarios', 'reaccion', 'reacciones')):
            self.intent = 'comments'
            date_from, date_to = self._date_range()
            domain = [
                ('company_id', '=', self.company_id.id), ('interaction_type', '=', 'comment'),
                ('interaction_date', '>=', datetime.combine(date_from, datetime.min.time())),
                ('interaction_date', '<=', datetime.combine(date_to, datetime.max.time())),
            ]
            if self.platform_filter != 'all':
                domain.append(('platform', '=', self.platform_filter))
            comments = self.env['marketing.social.interaction'].search(domain)
            pending = comments.filtered(lambda item: item.response_state == 'pending')
            commercial = comments.filtered(lambda item: item.intent == 'price')
            return _(
                'Encontré %s comentario(s): %s pendiente(s) de respuesta y %s con intención de precio o cotización. '
                'La prioridad es atender los pendientes comerciales y medir cuántos pasan a una oportunidad.'
            ) % (self._number(len(comments)), self._number(len(pending)), self._number(len(commercial)))
        if any(word in normalized for word in ('seguidor', 'audiencia', 'alcance', 'impresion', 'vista')):
            self.intent = 'audience'
            reach = sum(metric.reach for _publication, metric in rows)
            impressions = sum(metric.impressions for _publication, metric in rows)
            views = sum(metric.views for _publication, metric in rows)
            return _(
                'En %s hay un alcance acumulado de %s, %s impresiones y %s reproducciones. '
                'La diferencia entre alcance e impresiones ayuda a detectar frecuencia de exposición; úsala para ajustar la repetición de los contenidos.'
            ) % (self._platform_text(), self._number(reach), self._number(impressions), self._number(views))
        self.intent = 'engagement'
        reach = sum(metric.reach for _publication, metric in rows)
        interactions = sum(metric.total_interactions for _publication, metric in rows)
        likes = sum(metric.likes for _publication, metric in rows)
        comments = sum(metric.comments for _publication, metric in rows)
        shares = sum(metric.shares for _publication, metric in rows)
        return _(
            'Resumen de %s: %s publicaciones, %s de alcance y %s interacciones. '
            'Engagement: %.2f%%; me gusta: %s; comentarios: %s; compartidos: %s. '
            'Pregunta por «mejor publicación», «tendencias» o «comentarios pendientes» para profundizar.'
        ) % (
            self._platform_text(), self._number(len(rows)), self._number(reach), self._number(interactions),
            interactions / reach * 100 if reach else 0.0, self._number(likes),
            self._number(comments), self._number(shares),
        )

    def action_send_message(self):
        self.ensure_one()
        question = (self.draft_message or '').strip()
        if not question:
            raise UserError(_('Escribe una pregunta antes de enviarla.'))
        next_sequence = max(self.chat_message_ids.mapped('sequence') or [0]) + 1
        self.env['marketing.social.agent.message'].create({
            'chat_id': self.id, 'sequence': next_sequence,
            'speaker': 'user', 'body': question,
        })
        try:
            answer = self._answer_question(question)
            sources = self.source_publication_ids.sorted('published_at', reverse=True)
            source_summary = _('Respuesta calculada con %s publicación(es) y su última métrica disponible.') % len(sources)
            if self.intent == 'inbox':
                source_summary = _('Respuesta calculada con las cuentas, conversaciones y mensajes sociales sincronizados.')
            elif self.intent == 'quality':
                source_summary = _('Respuesta calculada con las instantáneas de calidad de métricas del período.')
            elif not sources and self.intent == 'audience':
                source_summary = _('Respuesta calculada con el catálogo externo de vehículos sincronizado.')
            if sources:
                source_summary += ' ' + _('Fuentes: %s.') % ', '.join(sources.mapped('name')[:5])
            self.env['marketing.social.agent.message'].create({
                'chat_id': self.id, 'sequence': next_sequence + 1,
                'speaker': 'agent', 'body': answer,
            })
            self.write({
                'draft_message': False, 'answer': answer, 'source_summary': source_summary,
                'state': 'answered',
            })
        except Exception as exc:
            self.write({'state': 'error', 'answer': False})
            raise UserError(_('No se pudo analizar la consulta: %s') % exc) from exc
        return {
            'type': 'ir.actions.act_window', 'name': _('Agente de marketing'),
            'res_model': self._name, 'view_mode': 'form', 'res_id': self.id,
            'target': 'current',
        }

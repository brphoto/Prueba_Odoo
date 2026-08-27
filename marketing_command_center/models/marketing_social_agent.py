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
    ], string='Consulta interpretada', readonly=True)
    message_ids = fields.One2many(
        'marketing.social.agent.message', 'chat_id', string='Conversación', readonly=True)
    message_count = fields.Integer(compute='_compute_message_count', string='Mensajes')
    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True,
        default=lambda self: self.env.company, index=True)

    @api.depends('message_ids')
    def _compute_message_count(self):
        for record in self:
            record.message_count = len(record.message_ids)

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
        rows = []
        for publication in publications:
            metrics = publication.metric_ids.filtered(
                lambda metric: date_from <= metric.snapshot_date <= date_to).sorted('snapshot_date')
            if metrics:
                rows.append((publication, metrics[-1]))
        return rows

    def _number(self, value):
        return '{:,.0f}'.format(value or 0).replace(',', '.')

    def _percent(self, value):
        return ('%.2f' % (value or 0)).replace('.', ',')

    def _platform_text(self):
        return 'todas las redes' if self.platform_filter == 'all' else PLATFORM_LABELS.get(self.platform_filter, self.platform_filter)

    def _answer_question(self, question):
        normalized = self._normalize(question)
        rows = self._rows()
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
        next_sequence = max(self.message_ids.mapped('sequence') or [0]) + 1
        self.env['marketing.social.agent.message'].create({
            'chat_id': self.id, 'sequence': next_sequence,
            'speaker': 'user', 'body': question,
        })
        try:
            answer = self._answer_question(question)
            self.env['marketing.social.agent.message'].create({
                'chat_id': self.id, 'sequence': next_sequence + 1,
                'speaker': 'agent', 'body': answer,
            })
            self.write({'draft_message': False, 'answer': answer, 'state': 'answered'})
        except Exception as exc:
            self.write({'state': 'error', 'answer': False})
            raise UserError(_('No se pudo analizar la consulta: %s') % exc) from exc
        return {
            'type': 'ir.actions.act_window', 'name': _('Agente de marketing'),
            'res_model': self._name, 'view_mode': 'form', 'res_id': self.id,
            'target': 'current',
        }

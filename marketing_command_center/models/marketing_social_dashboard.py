from datetime import datetime, timedelta

from odoo import _, api, fields, models

from .marketing_social_constants import PLATFORM_LABELS


class MarketingSocialDashboard(models.Model):
    _name = 'marketing.social.dashboard'
    _description = 'Centro de mando de marketing social'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(string='Panel', required=True, default='Centro de mando de marketing')
    period_days = fields.Integer(string='Período (días)', default=30, required=True)
    platform_filter = fields.Selection(
        [('all', 'Todas las redes')] + list(PLATFORM_LABELS.items()),
        string='Red analizada', default='all', required=True)
    date_from = fields.Date(compute='_compute_period', string='Desde')
    date_to = fields.Date(compute='_compute_period', string='Hasta')
    last_refresh_at = fields.Datetime(string='Última actualización', readonly=True)
    data_state = fields.Selection([
        ('empty', 'Sin datos'), ('ready', 'Datos disponibles'), ('demo', 'Datos demo'),
    ], string='Estado', default='empty', readonly=True)
    publication_count = fields.Integer(string='Publicaciones', readonly=True)
    account_count = fields.Integer(string='Cuentas activas', readonly=True)
    reach_total = fields.Integer(string='Alcance total', readonly=True)
    impressions_total = fields.Integer(string='Impresiones', readonly=True)
    views_total = fields.Integer(string='Reproducciones', readonly=True)
    interactions_total = fields.Integer(string='Interacciones', readonly=True)
    engagement_rate = fields.Float(string='Engagement (%)', readonly=True)
    pending_comments = fields.Integer(string='Comentarios pendientes', readonly=True)
    leads_total = fields.Integer(string='Oportunidades atribuidas', readonly=True)
    sales_total = fields.Monetary(string='Ventas atribuidas', currency_field='currency_id', readonly=True)
    currency_id = fields.Many2one(
        'res.currency', string='Moneda', default=lambda self: self.env.company.currency_id)
    top_publication_id = fields.Many2one(
        'marketing.social.publication', string='Publicación destacada', readonly=True)
    top_publication_rate = fields.Float(string='Engagement destacado (%)', readonly=True)
    top_platform = fields.Char(string='Red destacada', readonly=True)
    strategy_summary = fields.Text(string='Lectura estratégica', readonly=True)
    comparison_summary = fields.Text(string='Comparación con el período anterior', readonly=True)
    engagement_alert_threshold = fields.Float(
        string='Alertar si engagement es menor a (%)', default=2.0,
        help='Deja 0 para no generar esta alerta.')
    pending_comments_alert_threshold = fields.Integer(
        string='Alertar desde comentarios pendientes', default=5,
        help='Deja 0 para no generar esta alerta.')
    alert_ids = fields.One2many(
        'marketing.social.alert', 'dashboard_id', string='Alertas', readonly=True)
    open_alert_count = fields.Integer(
        compute='_compute_open_alert_count', string='Alertas abiertas')
    previous_reach_total = fields.Integer(string='Alcance período anterior', readonly=True)
    previous_interactions_total = fields.Integer(string='Interacciones período anterior', readonly=True)
    previous_engagement_rate = fields.Float(string='Engagement período anterior (%)', readonly=True)
    reach_delta_pct = fields.Float(string='Variación alcance (%)', readonly=True)
    interactions_delta_pct = fields.Float(string='Variación interacciones (%)', readonly=True)
    engagement_delta = fields.Float(string='Variación engagement (puntos)', readonly=True)
    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True,
        default=lambda self: self.env.company, index=True)

    @api.depends('period_days')
    def _compute_period(self):
        for record in self:
            days = max(record.period_days or 30, 1)
            record.date_to = fields.Date.context_today(record)
            record.date_from = record.date_to - timedelta(days=days - 1)

    @api.depends('alert_ids.state')
    def _compute_open_alert_count(self):
        for record in self:
            record.open_alert_count = len(record.alert_ids.filtered(lambda alert: alert.state == 'open'))

    def _latest_metrics(self, date_from, date_to):
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

    def action_refresh(self):
        for record in self:
            record.ensure_one()
            record._compute_period()
            rows = record._latest_metrics(record.date_from, record.date_to)
            period_size = max(record.period_days or 30, 1)
            previous_to = record.date_from - timedelta(days=1)
            previous_from = previous_to - timedelta(days=period_size - 1)
            previous_rows = record._latest_metrics(previous_from, previous_to)
            reach = sum(metric.reach for _publication, metric in rows)
            interactions = sum(metric.total_interactions for _publication, metric in rows)
            previous_reach = sum(metric.reach for _publication, metric in previous_rows)
            previous_interactions = sum(metric.total_interactions for _publication, metric in previous_rows)
            previous_engagement = (
                previous_interactions / previous_reach * 100 if previous_reach else 0.0)
            top = max(rows, key=lambda item: item[1].engagement_rate, default=(False, False))
            pending_domain = [
                ('company_id', '=', record.company_id.id),
                ('response_state', '=', 'pending'),
                ('interaction_type', '=', 'comment'),
                ('interaction_date', '>=', datetime.combine(record.date_from, datetime.min.time())),
                ('interaction_date', '<=', datetime.combine(record.date_to, datetime.max.time())),
            ]
            if record.platform_filter != 'all':
                pending_domain.append(('platform', '=', record.platform_filter))
            pending = self.env['marketing.social.interaction'].search_count(pending_domain)
            engagement = interactions / reach * 100 if reach else 0.0
            record.write({
                'last_refresh_at': fields.Datetime.now(),
                'data_state': 'ready' if rows else 'empty',
                'publication_count': len(rows),
                'account_count': self.env['marketing.social.account'].search_count([
                    ('company_id', '=', record.company_id.id), ('active', '=', True),
                ]),
                'reach_total': reach,
                'impressions_total': sum(metric.impressions for _publication, metric in rows),
                'views_total': sum(metric.views for _publication, metric in rows),
                'interactions_total': interactions,
                'engagement_rate': engagement,
                'pending_comments': pending,
                'leads_total': sum(metric.leads for _publication, metric in rows),
                'sales_total': sum(metric.sales_amount for _publication, metric in rows),
                'top_publication_id': top[0].id if top[0] else False,
                'top_publication_rate': top[1].engagement_rate if top[1] else 0.0,
                'top_platform': top[0].platform if top[0] else False,
                'strategy_summary': record._strategy_summary(rows, pending),
                'comparison_summary': record._comparison_summary(
                    reach, previous_reach, interactions, previous_interactions,
                    engagement, previous_engagement),
                'previous_reach_total': previous_reach,
                'previous_interactions_total': previous_interactions,
                'previous_engagement_rate': previous_engagement,
                'reach_delta_pct': record._variation(reach, previous_reach),
                'interactions_delta_pct': record._variation(interactions, previous_interactions),
                'engagement_delta': engagement - previous_engagement,
            })
            record._refresh_alerts(rows, pending, engagement)
        return True

    def _variation(self, current, previous):
        return ((current - previous) / previous * 100) if previous else (100.0 if current else 0.0)

    def _comparison_summary(self, reach, previous_reach, interactions, previous_interactions,
                            engagement, previous_engagement):
        if not previous_reach and not previous_interactions:
            return _('No hay datos del período anterior para comparar. La comparación comenzará cuando existan dos períodos con métricas.')
        return _(
            'Frente al período anterior, el alcance varió %.2f%%, las interacciones %.2f%% '
            'y el engagement cambió %.2f punto(s).'
        ) % (
            self._variation(reach, previous_reach),
            self._variation(interactions, previous_interactions),
            engagement - previous_engagement,
        )

    def _refresh_alerts(self, rows, pending, engagement):
        Alert = self.env['marketing.social.alert']
        active_types = set()
        if not rows:
            active_types.add('no_data')
            self._upsert_alert(Alert, 'no_data', 'info', _('Sin datos en el período'),
                              _('No se encontraron publicaciones con métricas para los filtros actuales.'))
        elif self.engagement_alert_threshold and engagement < self.engagement_alert_threshold:
            active_types.add('low_engagement')
            self._upsert_alert(
                Alert, 'low_engagement', 'warning', _('Engagement por debajo del objetivo'),
                _('El engagement actual es %.2f%% y el umbral configurado es %.2f%%.') %
                (engagement, self.engagement_alert_threshold))
        if self.pending_comments_alert_threshold and pending >= self.pending_comments_alert_threshold:
            active_types.add('pending_comments')
            self._upsert_alert(
                Alert, 'pending_comments', 'critical', _('Comentarios pendientes de atención'),
                _('%s comentario(s) requieren respuesta.') % pending)
        stale = self.alert_ids.filtered(lambda alert: alert.state == 'open' and alert.alert_type not in active_types)
        stale.write({'state': 'resolved', 'resolved_at': fields.Datetime.now()})

    def _upsert_alert(self, Alert, alert_type, severity, title, details):
        alert = self.alert_ids.filtered(
            lambda item: item.alert_type == alert_type and item.state == 'open')[:1]
        values = {
            'alert_type': alert_type, 'severity': severity,
            'title': title, 'details': details,
        }
        if alert:
            alert.write(values)
        else:
            Alert.create(dict(values, dashboard_id=self.id, company_id=self.company_id.id))

    def _strategy_summary(self, rows, pending):
        if not rows:
            return _('No hay publicaciones con métricas en el período seleccionado. Carga datos demo o sincroniza una cuenta.')
        top = max(rows, key=lambda item: item[1].engagement_rate)
        platform = PLATFORM_LABELS.get(top[0].platform, top[0].platform)
        message = _(
            'La publicación destacada es «%s» en %s, con %.2f%% de engagement. '
            'Conviene revisar su tema, formato y horario para replicar la estrategia.'
        ) % (top[0].name, platform, top[1].engagement_rate)
        if pending:
            message += ' ' + (_('Hay %s comentario(s) pendiente(s) de atención.') % pending)
        return message

    def action_seed_demo_data(self):
        Account = self.env['marketing.social.account']
        Publication = self.env['marketing.social.publication']
        Metric = self.env['marketing.social.metric.snapshot']
        Interaction = self.env['marketing.social.interaction']
        Campaign = self.env['marketing.social.campaign']
        company = self.company_id
        demo_accounts = Account.search([('demo_account', '=', True), ('company_id', '=', company.id)])
        if demo_accounts:
            self.action_refresh()
            self.write({'data_state': 'demo'})
            return True
        account_values = [
            ('DEMO Instagram Marketing', 'instagram'),
            ('DEMO Facebook Empresa', 'facebook'),
            ('DEMO TikTok Empresa', 'tiktok'),
            ('DEMO YouTube Empresa', 'youtube'),
        ]
        accounts = {}
        for name, platform in account_values:
            accounts[platform] = Account.create({
                'name': name, 'platform': platform,
                'external_id': 'demo-%s' % platform,
                'connection_state': 'connected', 'demo_account': True,
                'follower_count': {'instagram': 4200, 'facebook': 6800, 'tiktok': 9100, 'youtube': 2400}.get(platform, 0),
                'company_id': company.id,
            })
        campaign = Campaign.create({
            'name': 'DEMO Campaña: Odoo para empresas', 'code': 'DEMO-ODOO',
            'objective': 'leads', 'company_id': company.id,
        })
        today = fields.Date.context_today(self)
        topics = [
            ('Cómo ordenar tu CRM en Odoo', 'reel', 18000, 4100, 710, 92, 84, 125),
            ('Errores comunes al implementar Odoo', 'post', 9200, 1850, 330, 48, 36, 52),
            ('Automatiza tu seguimiento comercial', 'video', 24500, 6900, 1250, 140, 175, 240),
            ('Caso real: migración a Odoo', 'reel', 31800, 8700, 1720, 210, 260, 330),
            ('Inventario y ventas conectados', 'post', 7600, 1400, 260, 35, 22, 31),
            ('Preguntas frecuentes de implementación', 'video', 12700, 2900, 520, 64, 48, 77),
            ('Qué incluye una consultoría Odoo', 'reel', 28600, 7900, 1510, 180, 230, 298),
            ('Consejos para reducir tareas manuales', 'post', 6900, 1200, 210, 22, 18, 27),
            ('Dashboard para tomar decisiones', 'video', 20400, 5400, 970, 115, 120, 190),
            ('Antes y después de una automatización', 'reel', 35200, 10100, 2110, 250, 310, 420),
            ('RFM para conocer a tus clientes', 'post', 8300, 1700, 290, 39, 30, 41),
            ('Cómo preparar una cotización', 'video', 15400, 3600, 650, 78, 82, 105),
        ]
        platforms = ['instagram', 'facebook', 'tiktok', 'youtube']
        for index, (topic, content_type, reach, impressions, likes, comments, shares, saves) in enumerate(topics):
            platform = platforms[index % len(platforms)]
            publication = Publication.create({
                'name': 'DEMO %02d - %s' % (index + 1, topic),
                'account_id': accounts[platform].id, 'campaign_id': campaign.id,
                'published_at': datetime.combine(today - timedelta(days=index * 2 + 1), datetime.min.time()),
                'content_type': content_type, 'caption': topic,
                'hashtags': '#Odoo #CRM #Automatización', 'demo_record': True,
            })
            Metric.create({
                'publication_id': publication.id, 'snapshot_date': today,
                'reach': reach, 'impressions': impressions, 'views': impressions * 2,
                'likes': likes, 'comments': comments, 'shares': shares, 'saves': saves,
                'clicks': likes // 2, 'leads': max(comments // 4, 1),
                'sales_amount': float(max(comments // 2, 1) * 20),
            })
            Interaction.create({
                'publication_id': publication.id, 'interaction_type': 'comment',
                'author_name': 'Usuario demo %02d' % (index + 1),
                'text': '¿Podemos recibir una cotización de este servicio?',
                'interaction_date': datetime.combine(today - timedelta(days=index), datetime.min.time()),
                'sentiment': 'positive', 'intent': 'price',
                'response_state': 'pending' if index % 3 == 0 else 'responded',
            })
        self.action_refresh()
        self.write({'data_state': 'demo'})
        self.message_post(body=_('Se cargaron 12 publicaciones demo, 12 métricas y 12 interacciones para validar el centro de mando.'))
        return True

    def action_open_agent(self):
        return {
            'type': 'ir.actions.act_window', 'name': _('Agente de marketing'),
            'res_model': 'marketing.social.agent.chat', 'view_mode': 'form',
            'target': 'current',
        }

    def action_open_publications(self):
        return {
            'type': 'ir.actions.act_window', 'name': _('Publicaciones'),
            'res_model': 'marketing.social.publication', 'view_mode': 'list,kanban,graph,pivot',
            'domain': [
                ('company_id', '=', self.company_id.id), ('active', '=', True),
                ('published_at', '>=', datetime.combine(self.date_from, datetime.min.time())),
                ('published_at', '<=', datetime.combine(self.date_to, datetime.max.time())),
            ] + ([('platform', '=', self.platform_filter)] if self.platform_filter != 'all' else []),
            'target': 'current',
        }

    def action_open_alerts(self):
        return {
            'type': 'ir.actions.act_window', 'name': _('Alertas de marketing'),
            'res_model': 'marketing.social.alert', 'view_mode': 'list,form',
            'domain': [('dashboard_id', '=', self.id)], 'target': 'current',
        }

    def action_open_import(self):
        return {
            'type': 'ir.actions.act_window', 'name': _('Importar datos sociales'),
            'res_model': 'marketing.social.import.wizard', 'view_mode': 'form',
            'target': 'new',
        }

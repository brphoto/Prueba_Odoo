from odoo import api, fields, models

from .marketing_social_constants import PLATFORM_SELECTION


class MarketingSocialPublication(models.Model):
    _name = 'marketing.social.publication'
    _description = 'Publicación de red social'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'published_at desc, id desc'

    name = fields.Char(string='Título o referencia', required=True, tracking=True)
    external_id = fields.Char(string='ID externo', index=True)
    account_id = fields.Many2one(
        'marketing.social.account', string='Cuenta', required=True,
        ondelete='restrict', tracking=True)
    platform = fields.Selection(
        PLATFORM_SELECTION, string='Red', related='account_id.platform', store=True, index=True)
    campaign_id = fields.Many2one('marketing.social.campaign', string='Campaña', ondelete='set null')
    published_at = fields.Datetime(string='Fecha de publicación', required=True, tracking=True)
    content_type = fields.Selection([
        ('post', 'Publicación'), ('reel', 'Reel / video corto'),
        ('story', 'Historia'), ('video', 'Video'), ('article', 'Artículo'),
    ], string='Formato', default='post')
    caption = fields.Text(string='Texto de la publicación')
    hashtags = fields.Char(string='Hashtags')
    url = fields.Char(string='Enlace')
    active = fields.Boolean(default=True)
    demo_record = fields.Boolean(string='Dato demo', default=False, readonly=True)
    company_id = fields.Many2one(
        'res.company', string='Compañía', related='account_id.company_id', store=True, index=True)
    metric_ids = fields.One2many(
        'marketing.social.metric.snapshot', 'publication_id', string='Historial de métricas')
    interaction_ids = fields.One2many(
        'marketing.social.interaction', 'publication_id', string='Interacciones')
    latest_metric_date = fields.Date(compute='_compute_latest_metrics', string='Métrica al')
    latest_reach = fields.Integer(compute='_compute_latest_metrics', string='Alcance')
    latest_impressions = fields.Integer(compute='_compute_latest_metrics', string='Impresiones')
    latest_views = fields.Integer(compute='_compute_latest_metrics', string='Reproducciones')
    latest_likes = fields.Integer(compute='_compute_latest_metrics', string='Me gusta')
    latest_comments = fields.Integer(compute='_compute_latest_metrics', string='Comentarios')
    latest_shares = fields.Integer(compute='_compute_latest_metrics', string='Compartidos')
    latest_saves = fields.Integer(compute='_compute_latest_metrics', string='Guardados')
    latest_engagement_rate = fields.Float(
        compute='_compute_latest_metrics', string='Engagement (%)')
    pending_interaction_count = fields.Integer(
        compute='_compute_latest_metrics', string='Pendientes')

    @api.depends('metric_ids', 'metric_ids.snapshot_date', 'metric_ids.reach',
                 'metric_ids.impressions', 'metric_ids.views', 'metric_ids.likes',
                 'metric_ids.comments', 'metric_ids.shares', 'metric_ids.saves',
                 'interaction_ids.response_state')
    def _compute_latest_metrics(self):
        for record in self:
            latest = record.metric_ids.sorted('snapshot_date')[-1:] or self.env['marketing.social.metric.snapshot']
            metric = latest[0] if latest else False
            record.latest_metric_date = metric.snapshot_date if metric else False
            record.latest_reach = metric.reach if metric else 0
            record.latest_impressions = metric.impressions if metric else 0
            record.latest_views = metric.views if metric else 0
            record.latest_likes = metric.likes if metric else 0
            record.latest_comments = metric.comments if metric else 0
            record.latest_shares = metric.shares if metric else 0
            record.latest_saves = metric.saves if metric else 0
            record.latest_engagement_rate = metric.engagement_rate if metric else 0.0
            record.pending_interaction_count = len(record.interaction_ids.filtered(
                lambda item: item.response_state == 'pending'))


class MarketingSocialMetricSnapshot(models.Model):
    _name = 'marketing.social.metric.snapshot'
    _description = 'Historial de métricas sociales'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'snapshot_date desc, id desc'

    publication_id = fields.Many2one(
        'marketing.social.publication', string='Publicación', required=True,
        ondelete='cascade', index=True)
    account_id = fields.Many2one(
        'marketing.social.account', string='Cuenta', related='publication_id.account_id',
        store=True, index=True)
    platform = fields.Selection(
        PLATFORM_SELECTION, string='Red', related='publication_id.platform', store=True, index=True)
    snapshot_date = fields.Date(string='Fecha de medición', required=True, index=True)
    reach = fields.Integer(string='Alcance', default=0)
    impressions = fields.Integer(string='Impresiones', default=0)
    views = fields.Integer(string='Reproducciones', default=0)
    likes = fields.Integer(string='Me gusta', default=0)
    comments = fields.Integer(string='Comentarios', default=0)
    shares = fields.Integer(string='Compartidos', default=0)
    saves = fields.Integer(string='Guardados', default=0)
    clicks = fields.Integer(string='Clics', default=0)
    leads = fields.Integer(string='Oportunidades atribuidas', default=0)
    sales_amount = fields.Monetary(string='Ventas atribuidas', currency_field='currency_id', default=0.0)
    currency_id = fields.Many2one(
        'res.currency', string='Moneda', related='publication_id.company_id.currency_id', store=True)
    total_interactions = fields.Integer(compute='_compute_rates', string='Interacciones')
    engagement_rate = fields.Float(compute='_compute_rates', string='Engagement (%)')
    company_id = fields.Many2one(
        'res.company', string='Compañía', related='publication_id.company_id', store=True, index=True)

    @api.depends('likes', 'comments', 'shares', 'saves', 'reach', 'impressions')
    def _compute_rates(self):
        for record in self:
            record.total_interactions = record.likes + record.comments + record.shares + record.saves
            denominator = record.reach or record.impressions
            record.engagement_rate = (
                record.total_interactions / denominator * 100 if denominator else 0.0
            )

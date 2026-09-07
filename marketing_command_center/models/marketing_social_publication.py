from odoo import _, api, fields, models
from odoo.exceptions import UserError

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
        string='Red', related='account_id.platform', store=True, index=True)
    campaign_id = fields.Many2one('marketing.social.campaign', string='Campaña', ondelete='set null')
    published_at = fields.Datetime(string='Fecha de publicación', required=True, tracking=True)
    content_type = fields.Selection([
        ('post', 'Publicación'), ('reel', 'Reel / video corto'),
        ('story', 'Historia'), ('video', 'Video'), ('article', 'Artículo'),
    ], string='Formato', default='post')
    caption = fields.Text(string='Texto de la publicación')
    hashtags = fields.Char(string='Hashtags')
    draft_caption = fields.Text(
        string='Borrador de edición',
        help='Texto que se quiere enviar a la red. El texto original se conserva hasta sincronizarlo.')
    edit_state = fields.Selection([
        ('original', 'Sin cambios'), ('draft', 'Borrador local'),
        ('synced', 'Sincronizado'), ('error', 'Error'),
    ], string='Estado de edición', default='original', tracking=True, readonly=True)
    edit_original_caption = fields.Text(string='Texto original', readonly=True)
    edit_last_error = fields.Text(string='Detalle de edición', readonly=True)
    edit_synced_at = fields.Datetime(string='Última edición sincronizada', readonly=True)
    url = fields.Char(string='Enlace')
    media_url = fields.Char(
        string='Vista previa multimedia',
        help='URL de la imagen o video entregada por la red social. Se conserva separada del enlace de la publicación.')
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
    latest_provider_engagement = fields.Integer(compute='_compute_latest_metrics', string='Engagement nativo')
    latest_engagement_rate = fields.Float(
        compute='_compute_latest_metrics', string='Engagement (%)')
    latest_metric_status = fields.Selection(
        selection=[
            ('verified', 'Verificada'), ('partial', 'Parcial'),
            ('unavailable', 'No disponible'), ('demo', 'Demo'),
        ], compute='_compute_latest_metrics', string='Calidad de métrica')
    latest_metric_note = fields.Char(
        compute='_compute_latest_metrics', string='Nota de métrica')
    pending_interaction_count = fields.Integer(
        compute='_compute_latest_metrics', string='Pendientes')

    _publication_external_unique = models.Constraint(
        'unique(account_id, external_id)',
        'La publicación externa ya existe en esta cuenta.')

    def action_open_publication(self):
        """Open the native publication URL in a separate browser tab."""
        self.ensure_one()
        if not self.url:
            raise UserError(_('Esta publicación no tiene un enlace externo disponible.'))
        return {
            'type': 'ir.actions.act_url',
            'url': self.url,
            'target': 'new',
        }

    def action_open_form(self):
        """Open this native Odoo record from a visual catalog card."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Publicación social'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_open_media(self):
        """Open the media preview URL, when the provider exposes one."""
        self.ensure_one()
        if not self.media_url:
            raise UserError(_('Esta publicación no tiene una imagen o video disponible para previsualizar.'))
        return {
            'type': 'ir.actions.act_url',
            'url': self.media_url,
            'target': 'new',
        }

    def action_prepare_edit(self):
        """Prepare a local draft without changing the social network."""
        for record in self:
            record.write({
                'draft_caption': record.caption or '',
                'edit_original_caption': record.caption or '',
                'edit_state': 'draft',
                'edit_last_error': False,
            })
        return True

    def action_save_edit_draft(self):
        for record in self:
            if record.draft_caption is None:
                raise UserError(_('Escribe un texto antes de guardar el borrador.'))
            record.write({
                'edit_state': 'draft',
                'edit_last_error': False,
                'edit_original_caption': record.edit_original_caption or record.caption or '',
            })
            record.message_post(body=_('Se guardo un borrador local de edicion. Aun no se modifico la red social.'))
        return True

    def action_discard_edit_draft(self):
        for record in self:
            record.write({
                'draft_caption': False,
                'edit_state': 'original',
                'edit_last_error': False,
            })
        return True

    @api.depends('metric_ids', 'metric_ids.snapshot_date', 'metric_ids.metric_status',
                 'metric_ids.provider_error', 'metric_ids.reach',
                 'metric_ids.impressions', 'metric_ids.views', 'metric_ids.likes',
                 'metric_ids.comments', 'metric_ids.shares', 'metric_ids.saves', 'metric_ids.provider_engagement',
                 'interaction_ids.response_state')
    def _compute_latest_metrics(self):
        # La ultima instantanea de cada publicacion en dos consultas para
        # todo el lote. Antes se cargaba en memoria el historial COMPLETO de
        # metricas de cada publicacion solo para quedarse con la mas
        # reciente: la lista, el kanban y el grafico de publicaciones
        # traian todas las mediciones de todas las filas de la pagina.
        Snapshot = self.env['marketing.social.metric.snapshot']
        publication_ids = [record.id for record in self._origin if record.id]
        latest_by_publication = {}
        pending_by_publication = {}
        if publication_ids:
            Snapshot.flush_model(['publication_id', 'snapshot_date'])
            self.env.cr.execute("""
                SELECT DISTINCT ON (publication_id) publication_id, id
                  FROM marketing_social_metric_snapshot
                 WHERE publication_id IN %s
              ORDER BY publication_id, snapshot_date DESC, id DESC
            """, (tuple(publication_ids),))
            latest_by_publication = {
                publication_id: Snapshot.browse(snapshot_id)
                for publication_id, snapshot_id in self.env.cr.fetchall()
            }
            pending_by_publication = {
                publication.id: count
                for publication, count in self.env['marketing.social.interaction']._read_group(
                    [('publication_id', 'in', publication_ids),
                     ('response_state', '=', 'pending')],
                    ['publication_id'], ['__count'])
                if publication
            }
        for record in self:
            metric = latest_by_publication.get(record._origin.id) or False
            record.latest_metric_date = metric.snapshot_date if metric else False
            record.latest_reach = metric.reach if metric else 0
            record.latest_impressions = metric.impressions if metric else 0
            record.latest_views = metric.views if metric else 0
            record.latest_likes = metric.likes if metric else 0
            record.latest_comments = metric.comments if metric else 0
            record.latest_shares = metric.shares if metric else 0
            record.latest_saves = metric.saves if metric else 0
            record.latest_provider_engagement = metric.provider_engagement if metric else 0
            record.latest_engagement_rate = metric.engagement_rate if metric else 0.0
            record.latest_metric_status = metric.metric_status if metric else 'unavailable'
            record.latest_metric_note = metric.provider_error if metric else (
                'No existe una instantánea para esta publicación.' if not metric else False)
            record.pending_interaction_count = pending_by_publication.get(
                record._origin.id, 0)


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
        string='Red', related='publication_id.platform', store=True, index=True)
    snapshot_date = fields.Date(string='Fecha de medición', required=True, index=True)
    reach = fields.Integer(string='Alcance', default=0)
    impressions = fields.Integer(string='Impresiones', default=0)
    views = fields.Integer(string='Reproducciones', default=0)
    likes = fields.Integer(string='Me gusta', default=0)
    comments = fields.Integer(string='Comentarios', default=0)
    shares = fields.Integer(string='Compartidos', default=0)
    saves = fields.Integer(string='Guardados', default=0)
    provider_engagement = fields.Integer(string='Engagement nativo', default=0)
    clicks = fields.Integer(string='Clics', default=0)
    leads = fields.Integer(string='Oportunidades atribuidas', default=0)
    sales_amount = fields.Monetary(string='Ventas atribuidas', currency_field='currency_id', default=0.0)
    source = fields.Selection([
        ('local', 'Importación local'), ('meta', 'Meta'), ('demo', 'Demo'),
    ], string='Origen', default='local', required=True, index=True)
    metric_status = fields.Selection([
        ('verified', 'Verificada por el proveedor'),
        ('partial', 'Parcial: contadores básicos'),
        ('unavailable', 'No disponible en el proveedor'),
        ('demo', 'Dato demo'),
    ], string='Calidad de métrica', default='unavailable', required=True, index=True,
        help='Distingue un cero real de una métrica que Meta no pudo entregar.')
    provider_error = fields.Char(
        string='Detalle del proveedor', readonly=True,
        help='Explica permisos, métricas no disponibles o errores de la API.')
    fetched_at = fields.Datetime(string='Consultada el', readonly=True)
    currency_id = fields.Many2one(
        'res.currency', string='Moneda', related='publication_id.company_id.currency_id', store=True)
    @api.model
    def _latest_per_publication(self, publications, date_from, date_to):
        """[(publicacion, instantanea)] con la ultima medicion del periodo.

        El panel y el agente hacian esto por separado, cada uno recorriendo
        publicacion por publicacion y cargando su historial completo de
        metricas en memoria para quedarse con la ultima. Con un mes de
        mediciones diarias eso es traer todo el historico para leer un
        registro por fila. DISTINCT ON lo resuelve en una consulta.
        """
        if not publications:
            return []
        self.flush_model(['publication_id', 'snapshot_date'])
        self.env.cr.execute("""
            SELECT DISTINCT ON (publication_id) publication_id, id
              FROM marketing_social_metric_snapshot
             WHERE publication_id IN %s
               AND snapshot_date >= %s
               AND snapshot_date <= %s
          ORDER BY publication_id, snapshot_date DESC, id DESC
        """, (tuple(publications.ids), date_from, date_to))
        latest_ids = dict(self.env.cr.fetchall())
        if not latest_ids:
            return []
        # Un solo SELECT para todas las instantaneas elegidas.
        self.browse(list(latest_ids.values())).mapped('reach')
        return [
            (publication, self.browse(latest_ids[publication.id]))
            for publication in publications
            if publication.id in latest_ids
        ]

    total_interactions = fields.Integer(compute='_compute_rates', string='Interacciones')
    engagement_rate = fields.Float(compute='_compute_rates', string='Engagement (%)')
    company_id = fields.Many2one(
        'res.company', string='Compañía', related='publication_id.company_id', store=True, index=True)

    _metric_date_unique = models.Constraint(
        'unique(publication_id, snapshot_date)',
        'Ya existe una métrica para esta publicación y fecha.')

    @api.depends('likes', 'comments', 'shares', 'saves', 'reach', 'impressions')
    def _compute_rates(self):
        for record in self:
            record.total_interactions = record.provider_engagement or (
                record.likes + record.comments + record.shares + record.saves)
            denominator = record.reach or record.impressions
            record.engagement_rate = (
                record.total_interactions / denominator * 100 if denominator else 0.0
            )

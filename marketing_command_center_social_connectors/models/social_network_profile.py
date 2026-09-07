import time
from datetime import datetime, timezone

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .social_network_api import SocialNetworkApiError


def _social_datetime(value):
    if not value:
        return False
    try:
        if isinstance(value, (int, float)) or str(value).isdigit():
            return datetime.fromtimestamp(float(value), tz=timezone.utc).replace(tzinfo=None)
        return datetime.fromisoformat(str(value).replace('Z', '+00:00').replace('+0000', '+00:00')).replace(tzinfo=None)
    except ValueError:
        return False


class MarketingSocialNetworkProfile(models.Model):
    _name = 'marketing.social.network.profile'
    _description = 'Cuenta descubierta de red social'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'active desc, name'

    name = fields.Char(string='Nombre de la cuenta', required=True, tracking=True)
    connection_id = fields.Many2one('marketing.social.network.connection', string='Conexión', required=True,
                                    ondelete='cascade', index=True, tracking=True)
    platform = fields.Selection(related='connection_id.platform', store=True, index=True)
    external_id = fields.Char(string='ID externo', required=True, index=True)
    username = fields.Char(string='Usuario o identificador público')
    profile_url = fields.Char(string='URL del perfil')
    follower_count = fields.Integer(string='Seguidores', readonly=True)
    sync_days = fields.Integer(string='Días a sincronizar', related='connection_id.sync_days', readonly=False)
    active = fields.Boolean(default=True, tracking=True)
    state = fields.Selection([
        ('pending', 'Pendiente'), ('connected', 'Conectada'), ('error', 'Con error'),
    ], string='Estado', default='pending', tracking=True, readonly=True)
    last_sync_at = fields.Datetime(string='Última sincronización', readonly=True)
    last_error = fields.Text(string='Último detalle técnico', readonly=True)
    last_sync_summary = fields.Char(string='Resumen de la última sincronización', readonly=True)
    last_sync_duration = fields.Float(string='Duración última sincronización (s)', readonly=True)
    sync_log_ids = fields.One2many(
        'marketing.social.network.sync.log', 'profile_id', string='Historial de sincronizaciones', readonly=True)
    sync_log_count = fields.Integer(string='Ejecuciones', compute='_compute_sync_log_count')
    last_posts_count = fields.Integer(string='Publicaciones procesadas', readonly=True)
    last_comments_count = fields.Integer(string='Comentarios procesados', readonly=True)
    social_account_id = fields.Many2one('marketing.social.account', string='Cuenta en centro de mando', readonly=True,
                                        ondelete='set null')
    company_id = fields.Many2one('res.company', related='connection_id.company_id', store=True, index=True)
    uploads_playlist_id = fields.Char(string='Playlist de vídeos', readonly=True)

    _profile_unique = models.Constraint('unique(connection_id, external_id)', 'La cuenta ya existe en esta conexión.')

    @api.depends('sync_log_ids')
    def _compute_sync_log_count(self):
        for record in self:
            record.sync_log_count = len(record.sync_log_ids)

    @api.model
    def _upsert_from_adapter(self, connection, values):
        external_id = values.get('external_id')
        if not external_id:
            return self.env['marketing.social.network.profile']
        profile = self.search([('connection_id', '=', connection.id), ('external_id', '=', external_id)], limit=1)
        vals = {
            'name': values.get('name') or external_id,
            'external_id': external_id,
            'username': values.get('username') or False,
            'profile_url': values.get('profile_url') or False,
            'follower_count': int(values.get('follower_count') or 0),
            'state': 'pending',
            'uploads_playlist_id': values.get('uploads_playlist_id') or False,
        }
        if profile:
            profile.write(vals)
        else:
            profile = self.create(dict(vals, connection_id=connection.id))
        profile._ensure_social_account()
        return profile

    def _ensure_social_account(self):
        self.ensure_one()
        Account = self.env['marketing.social.account']
        account = self.social_account_id or Account.search([
            ('platform', '=', self.platform), ('external_id', '=', self.external_id),
            ('company_id', '=', self.company_id.id),
        ], limit=1)
        vals = {
            'name': self.name, 'platform': self.platform, 'external_id': self.external_id,
            'profile_url': self.profile_url, 'follower_count': self.follower_count,
            'connection_state': 'pending', 'company_id': self.company_id.id,
        }
        if account:
            account.write(vals)
        else:
            account = Account.create(vals)
        self.social_account_id = account
        return account

    def action_test_profile(self):
        for record in self:
            try:
                values = record.connection_id._adapter().profile(record.connection_id._adapter().test())
            except SocialNetworkApiError as error:
                record.write({'state': 'error', 'last_error': str(error)})
                raise UserError(str(error)) from error
            record.write({
                'name': values.get('name') or record.name,
                'username': values.get('username') or record.username,
                'profile_url': values.get('profile_url') or record.profile_url,
                'follower_count': int(values.get('follower_count') or 0),
                'state': 'connected', 'last_error': False,
            })
            record._ensure_social_account()
        return True

    def action_sync_profile(self):
        for record in self:
            record._sync_one_profile()
        return True

    def action_open_sync_logs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _('Historial de sincronizaciones'),
            'res_model': 'marketing.social.network.sync.log', 'view_mode': 'list,form',
            'domain': [('profile_id', '=', self.id)],
            'context': {'default_profile_id': self.id, 'default_connection_id': self.connection_id.id},
        }

    def _sync_one_profile(self):
        self.ensure_one()
        adapter = self.connection_id._adapter()
        account = self._ensure_social_account()
        started_at = fields.Datetime.now()
        timer = time.perf_counter()
        Log = self.env['marketing.social.network.sync.log']
        log = Log.create({
            'name': _('Sincronización de %s') % self.name,
            'connection_id': self.connection_id.id, 'profile_id': self.id,
            'started_at': started_at,
        })
        try:
            publications = adapter.publications(self)
        except SocialNetworkApiError as error:
            duration = time.perf_counter() - timer
            self.write({'state': 'error', 'last_error': str(error), 'last_sync_duration': duration})
            account.write({'connection_state': 'error', 'sync_message': str(error)})
            log.write({
                'state': 'error', 'finished_at': fields.Datetime.now(),
                'duration_seconds': duration, 'error_message': str(error),
            })
            raise
        except Exception as error:
            duration = time.perf_counter() - timer
            message = _('Error inesperado al sincronizar: %s') % error
            self.write({'state': 'error', 'last_error': message, 'last_sync_duration': duration})
            account.write({'connection_state': 'error', 'sync_message': message})
            log.write({
                'state': 'error', 'finished_at': fields.Datetime.now(),
                'duration_seconds': duration, 'error_message': message,
            })
            raise UserError(message) from error
        comments_count = 0
        for values in publications:
            publication = self._upsert_publication(account, values)
            self._upsert_metric(publication, values.get('metrics') or {})
            for comment in getattr(adapter, 'comments', lambda _id: [])(values.get('external_id')):
                if comment.get('external_id'):
                    self._upsert_interaction(publication, comment)
                    comments_count += 1
        summary = _('%s publicación(es) y %s comentario(s) procesado(s).') % (len(publications), comments_count)
        now = fields.Datetime.now()
        self.write({
            'state': 'connected', 'last_sync_at': now, 'last_error': False,
            'last_sync_summary': summary, 'last_posts_count': len(publications),
            'last_comments_count': comments_count,
            'last_sync_duration': time.perf_counter() - timer,
        })
        account.write({
            'name': self.name, 'profile_url': self.profile_url,
            'follower_count': self.follower_count, 'connection_state': 'connected',
            'last_sync_at': now, 'sync_message': 'Sincronización correcta',
        })
        self.connection_id.write({'last_sync_at': now, 'state': 'connected', 'last_error': False})
        self.message_post(body=_('Sincronización correcta: %s') % summary)
        log.write({
            'state': 'success', 'finished_at': fields.Datetime.now(),
            'duration_seconds': time.perf_counter() - timer,
            'publications_count': len(publications), 'interactions_count': comments_count,
        })
        return len(publications)

    def _upsert_publication(self, account, values):
        Publication = self.env['marketing.social.publication']
        publication = Publication.search([
            ('external_id', '=', values.get('external_id')), ('account_id', '=', account.id),
        ], limit=1)
        vals = {
            'name': values.get('name') or _('Publicación social'), 'external_id': values.get('external_id'),
            'account_id': account.id, 'published_at': _social_datetime(values.get('published_at')) or fields.Datetime.now(),
            'content_type': values.get('content_type') or 'post', 'caption': values.get('caption') or False,
            'url': values.get('url') or False,
        }
        if publication:
            publication.write(vals)
        else:
            publication = Publication.create(vals)
        return publication

    def _upsert_metric(self, publication, values):
        Metric = self.env['marketing.social.metric.snapshot']
        today = fields.Date.context_today(self)
        vals = {
            'snapshot_date': today, 'reach': int(values.get('reach') or 0),
            'impressions': int(values.get('impressions') or 0), 'views': int(values.get('views') or 0),
            'likes': int(values.get('likes') or 0), 'comments': int(values.get('comments') or 0),
            'shares': int(values.get('shares') or 0), 'saves': int(values.get('saves') or 0),
            'clicks': int(values.get('clicks') or 0), 'leads': int(values.get('leads') or 0),
            'sales_amount': float(values.get('sales_amount') or 0.0),
        }
        metric = Metric.search([('publication_id', '=', publication.id), ('snapshot_date', '=', today)], limit=1)
        if metric:
            metric.write(vals)
        else:
            Metric.create(dict(vals, publication_id=publication.id))

    def _upsert_interaction(self, publication, values):
        Interaction = self.env['marketing.social.interaction']
        vals = {
            'publication_id': publication.id, 'interaction_type': values.get('interaction_type') or 'comment',
            'external_id': values.get('external_id'), 'text': values.get('text') or False,
            'author_name': values.get('author_name') or False,
            'interaction_date': _social_datetime(values.get('interaction_date')) or fields.Datetime.now(),
        }
        existing = Interaction.search([
            ('publication_id', '=', publication.id), ('external_id', '=', values.get('external_id')),
        ], limit=1)
        if existing:
            existing.write(vals)
        else:
            Interaction.create(vals)

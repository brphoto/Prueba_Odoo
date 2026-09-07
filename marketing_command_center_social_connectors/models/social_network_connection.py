import time

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .social_network_api import ADAPTERS, SocialNetworkApiError


PLATFORM_SELECTION = [
    ('instagram', 'Instagram'), ('youtube', 'YouTube'),
    ('linkedin', 'LinkedIn'), ('tiktok', 'TikTok'),
]


class MarketingSocialNetworkConnection(models.Model):
    _name = 'marketing.social.network.connection'
    _description = 'Conexión de red social'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'active desc, platform, name'

    name = fields.Char(string='Nombre de la conexión', required=True, tracking=True)
    platform = fields.Selection(PLATFORM_SELECTION, string='Red social', required=True, tracking=True)
    client_id = fields.Char(string='ID de aplicación', groups='marketing_command_center_social_connectors.group_network_manager')
    client_secret = fields.Char(string='Secreto de aplicación', groups='marketing_command_center_social_connectors.group_network_manager')
    access_token = fields.Char(string='Token OAuth', groups='marketing_command_center_social_connectors.group_network_manager')
    api_key = fields.Char(string='API key', groups='marketing_command_center_social_connectors.group_network_manager')
    api_version = fields.Char(string='Versión API', help='Versión de API del proveedor, si aplica.')
    external_account_id = fields.Char(string='ID de organización/canal opcional')
    sync_days = fields.Integer(string='Días a sincronizar', default=30, required=True)
    active = fields.Boolean(default=True, tracking=True)
    state = fields.Selection([
        ('draft', 'Sin probar'), ('connected', 'Conectada'), ('error', 'Con error'),
    ], string='Estado', default='draft', tracking=True, readonly=True)
    profile_ids = fields.One2many('marketing.social.network.profile', 'connection_id', string='Cuentas')
    profile_count = fields.Integer(string='Cuentas', compute='_compute_profile_count')
    last_checked_at = fields.Datetime(string='Última comprobación', readonly=True)
    last_sync_at = fields.Datetime(string='Última sincronización', readonly=True)
    last_sync_duration = fields.Float(string='Duración última sincronización (s)', readonly=True)
    last_sync_publications = fields.Integer(string='Publicaciones última sincronización', readonly=True)
    last_sync_interactions = fields.Integer(string='Interacciones última sincronización', readonly=True)
    sync_log_count = fields.Integer(string='Ejecuciones', compute='_compute_sync_log_count')
    last_error = fields.Text(string='Último detalle técnico', readonly=True)
    company_id = fields.Many2one('res.company', string='Compañía', required=True,
                                 default=lambda self: self.env.company, index=True)

    @api.depends('profile_ids')
    def _compute_profile_count(self):
        for record in self:
            record.profile_count = len(record.profile_ids)

    @api.depends('profile_ids.sync_log_ids')
    def _compute_sync_log_count(self):
        Log = self.env['marketing.social.network.sync.log']
        for record in self:
            record.sync_log_count = Log.search_count([('connection_id', '=', record.id)])

    @api.constrains('sync_days')
    def _check_sync_days(self):
        for record in self:
            if not 1 <= record.sync_days <= 365:
                raise ValidationError(_('Los días a sincronizar deben estar entre 1 y 365.'))

    @api.constrains('platform')
    def _check_platform(self):
        for record in self:
            if record.platform not in dict(PLATFORM_SELECTION):
                raise ValidationError(_('Selecciona una red social válida.'))

    def _adapter(self):
        self.ensure_one()
        try:
            adapter_class = ADAPTERS[self.platform]
        except KeyError as error:
            raise UserError(_('Esta red todavía no tiene un conector instalado.')) from error
        return adapter_class(self)

    def _mark_error(self, error):
        message = str(error)
        self.write({'state': 'error', 'last_checked_at': fields.Datetime.now(), 'last_error': message})
        self.message_post(body=_('La red social reportó un error: %s') % message)

    def action_test_connection(self):
        for record in self:
            try:
                payload = record._adapter().test()
            except SocialNetworkApiError as error:
                record._mark_error(error)
                raise UserError(str(error)) from error
            record.write({'state': 'connected', 'last_checked_at': fields.Datetime.now(), 'last_error': False})
            record.message_post(body=_('Conexión de %s verificada.') % dict(PLATFORM_SELECTION).get(record.platform))
        return True

    def action_discover_accounts(self):
        Profile = self.env['marketing.social.network.profile']
        for record in self:
            try:
                profiles = record._adapter().discover_profiles()
            except SocialNetworkApiError as error:
                record._mark_error(error)
                raise UserError(str(error)) from error
            for values in profiles:
                Profile._upsert_from_adapter(record, values)
            record.write({'state': 'connected', 'last_checked_at': fields.Datetime.now(), 'last_error': False})
            record.message_post(body=_('%s cuenta(s) descubierta(s).') % len(profiles))
        return {
            'type': 'ir.actions.act_window', 'name': _('Cuentas descubiertas'),
            'res_model': 'marketing.social.network.profile', 'view_mode': 'list,form',
            'domain': [('connection_id', 'in', self.ids)],
        }

    def action_sync_all_profiles(self):
        for record in self:
            errors = []
            timer = time.perf_counter()
            publications = interactions = 0
            for profile in record.profile_ids.filtered('active'):
                try:
                    publications += profile._sync_one_profile()
                    interactions += profile.last_comments_count
                except (SocialNetworkApiError, UserError) as error:
                    errors.append('%s: %s' % (profile.name, error))
            record.write({
                'last_sync_at': fields.Datetime.now(),
                'state': 'error' if errors else 'connected',
                'last_error': '\n'.join(errors) or False,
                'last_sync_duration': time.perf_counter() - timer,
                'last_sync_publications': publications,
                'last_sync_interactions': interactions,
            })
        return True

    def action_open_sync_logs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _('Historial de sincronizaciones'),
            'res_model': 'marketing.social.network.sync.log',
            'view_mode': 'list,form',
            'domain': [('connection_id', '=', self.id)],
            'context': {'default_connection_id': self.id},
        }

    @api.model
    def _cron_sync_networks(self):
        for record in self.search([('active', '=', True), ('profile_ids.active', '=', True)]):
            record.action_sync_all_profiles()
        return True

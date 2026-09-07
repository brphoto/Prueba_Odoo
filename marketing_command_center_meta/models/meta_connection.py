from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .meta_api import MetaGraphClient, MetaGraphError
from .meta_constants import META_DEFAULT_API_VERSION


class MarketingMetaConnection(models.Model):
    _name = 'marketing.meta.connection'
    _description = 'Conexión de Meta para marketing social'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'active desc, name'

    name = fields.Char(string='Nombre de la conexión', required=True, tracking=True)
    app_id = fields.Char(string='ID de aplicación Meta', groups='marketing_command_center_meta.group_meta_manager')
    app_secret = fields.Char(
        string='Secreto de aplicación', groups='marketing_command_center_meta.group_meta_manager')
    user_access_token = fields.Char(
        string='Token de usuario Meta', groups='marketing_command_center_meta.group_meta_manager')
    api_version = fields.Char(string='Versión Graph API', default=META_DEFAULT_API_VERSION, required=True)
    active = fields.Boolean(default=True, tracking=True)
    state = fields.Selection([
        ('draft', 'Sin probar'), ('connected', 'Conectada'), ('error', 'Con error'),
    ], string='Estado', default='draft', tracking=True, readonly=True)
    last_checked_at = fields.Datetime(string='Última comprobación', readonly=True)
    last_sync_at = fields.Datetime(string='Última sincronización', readonly=True)
    last_error = fields.Text(string='Último detalle técnico', readonly=True)
    permissions_state = fields.Selection([
        ('unknown', 'No comprobados'), ('partial', 'Permisos parciales'), ('ready', 'Listos'),
    ], string='Permisos Meta', default='unknown', readonly=True, tracking=True)
    permissions_summary = fields.Text(string='Permisos detectados', readonly=True)
    last_permissions_check = fields.Datetime(string='Última comprobación de permisos', readonly=True)
    page_ids = fields.One2many('marketing.meta.page', 'connection_id', string='Páginas')
    page_count = fields.Integer(string='Páginas', compute='_compute_page_count')
    max_pages_per_run = fields.Integer(
        string='Páginas por lote', default=1, required=True,
        help='Cantidad máxima de páginas que se sincronizan por ejecución. Usa un número alto si realmente necesitas procesarlas todas; un lote pequeño evita tiempos de espera.')
    last_sync_summary = fields.Char(string='Resumen del último lote', readonly=True)
    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True,
        default=lambda self: self.env.company, index=True)

    @api.depends('page_ids')
    def _compute_page_count(self):
        for record in self:
            record.page_count = len(record.page_ids)

    @api.constrains('api_version')
    def _check_api_version(self):
        for record in self:
            if not record.api_version.startswith('v'):
                raise ValidationError(_('La versión de Graph API debe tener formato v25.0.'))

    @api.constrains('max_pages_per_run')
    def _check_max_pages_per_run(self):
        for record in self:
            if record.max_pages_per_run < 1 or record.max_pages_per_run > 100:
                raise ValidationError(_('Las páginas por lote deben estar entre 1 y 100.'))

    def _client(self):
        self.ensure_one()
        return MetaGraphClient(self.user_access_token, self.api_version)

    def _mark_error(self, message):
        self.write({
            'state': 'error', 'last_checked_at': fields.Datetime.now(), 'last_error': message,
        })
        self.message_post(body=_('Meta reportó un error: %s') % message)

    def action_test_connection(self):
        for record in self:
            try:
                data = record._client().request('me', {'fields': 'id,name'})
            except MetaGraphError as error:
                record._mark_error(str(error))
                raise UserError(str(error)) from error
            record.write({
                'state': 'connected', 'last_checked_at': fields.Datetime.now(), 'last_error': False,
            })
            record.message_post(body=_('Conexión Meta verificada: %s.') % (data.get('name') or data.get('id')))
        return True

    def action_check_permissions(self):
        """Consulta permisos sin modificar Meta ni exponer el token."""
        for record in self:
            try:
                payload = record._client().paged('me/permissions', {'limit': 100})
            except MetaGraphError as error:
                record.write({
                    'permissions_state': 'unknown',
                    'permissions_summary': str(error),
                    'last_permissions_check': fields.Datetime.now(),
                })
                raise UserError(str(error)) from error
            rows = payload.get('data') or []
            permissions = sorted(
                '%s: %s' % (item.get('permission'), item.get('status'))
                for item in rows if item.get('permission'))
            required = {
                'pages_read_engagement', 'pages_manage_metadata', 'pages_messaging',
                'instagram_basic', 'instagram_manage_comments', 'instagram_manage_insights',
                'instagram_manage_messages',
            }
            granted = {item.split(':', 1)[0] for item in permissions if item.endswith(': granted')}
            record.write({
                'permissions_state': 'ready' if required.intersection(granted) else 'partial',
                'permissions_summary': '\n'.join(permissions) or _('Meta no devolvió permisos visibles.'),
                'last_permissions_check': fields.Datetime.now(),
                'last_error': False,
            })
            record.message_post(body=_('Permisos Meta comprobados: %s.') % len(permissions))
        return True

    def action_discover_pages(self):
        Page = self.env['marketing.meta.page']
        for record in self:
            try:
                payload = record._client().paged('me/accounts', {
                    'fields': 'id,name,access_token,category,link,fan_count',
                    'limit': 100,
                })
            except MetaGraphError as error:
                record._mark_error(str(error))
                raise UserError(str(error)) from error
            found = 0
            for values in payload.get('data', []):
                page = Page._upsert_from_meta(record, values)
                found += bool(page)
            record.write({
                'state': 'connected', 'last_checked_at': fields.Datetime.now(), 'last_error': False,
            })
            record.message_post(body=_('%s página(s) descubierta(s) en Meta.') % found)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Páginas Meta'),
            'res_model': 'marketing.meta.page',
            'view_mode': 'list,form',
            'domain': [('connection_id', 'in', self.ids)],
        }

    def action_sync_all_pages(self):
        for record in self:
            pages = record.page_ids.filtered(lambda page: page.active).sorted(
                key=lambda page: page.last_sync_at or datetime.min)
            pages = pages[:record.max_pages_per_run]
            errors = []
            for page in pages:
                try:
                    page.action_sync_page()
                except (MetaGraphError, UserError) as error:
                    errors.append('%s: %s' % (page.name, error))
            record.write({
                'last_sync_at': fields.Datetime.now(),
                'state': 'error' if errors else 'connected',
                'last_error': '\n'.join(errors) or False,
                'last_sync_summary': _(
                    'Lote completado: %s página(s) procesada(s); %s pendiente(s); %s con error(es).') % (
                        len(pages), len(record.page_ids.filtered(lambda page: page.active)) - len(pages), len(errors)),
            })
            if errors:
                record.message_post(body=_('Sincronización parcial. %s página(s) con error.') % len(errors))
            else:
                record.message_post(body=record.last_sync_summary)
        return True

    def action_sync_all_inboxes(self):
        """Refresh only the social inboxes for every active discovered page."""
        for record in self:
            errors = []
            total_conversations = total_messages = 0
            pages = record.page_ids.filtered(lambda page: page.active).sorted(
                key=lambda page: page.last_sync_at or datetime.min)
            pages = pages[:record.max_pages_per_run]
            for page in pages:
                try:
                    page.action_sync_inbox()
                    total_conversations += page.last_conversations_count
                    total_messages += page.last_messages_count
                except (MetaGraphError, UserError) as error:
                    errors.append('%s: %s' % (page.name, error))
            record.write({
                'last_sync_at': fields.Datetime.now(),
                'state': 'error' if errors else 'connected',
                'last_error': '\n'.join(errors) or False,
                'last_sync_summary': _(
                    'Bandeja por lote: %s página(s), %s conversación(es), %s mensaje(s); %s pendiente(s); %s con error(es).') % (
                        len(pages), total_conversations, total_messages,
                        len(record.page_ids.filtered(lambda page: page.active)) - len(pages), len(errors)),
            })
            body = _(
                'Bandejas sincronizadas: %s conversación(es) y %s mensaje(s).') % (
                    total_conversations, total_messages)
            if errors:
                body += '<br/><b>%s</b><br/>%s' % (_('Avisos'), '<br/>'.join(errors))
            record.message_post(body=body)
        # La acción se ejecuta desde la interfaz: abrir la bandeja al terminar
        # hace visible el resultado y evita que una sincronización parezca vacía.
        return self.env.ref(
            'marketing_command_center.action_marketing_social_conversations').read()[0]

    @api.model
    def _cron_sync_meta_pages(self):
        for record in self.search([('active', '=', True), ('page_ids.active', '=', True)]):
            try:
                record.action_sync_all_pages()
            except (MetaGraphError, UserError) as error:
                record._mark_error(str(error))
        return True

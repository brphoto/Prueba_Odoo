from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .marketing_social_constants import PLATFORM_SELECTION


class MarketingSocialAccount(models.Model):
    _name = 'marketing.social.account'
    _description = 'Cuenta de red social'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'marketing.diagnostic.mixin']
    _order = 'platform, name'

    name = fields.Char(string='Nombre de la cuenta', required=True, tracking=True)
    platform = fields.Selection(PLATFORM_SELECTION, string='Red social', required=True, tracking=True)
    external_id = fields.Char(string='Identificador externo', index=True)
    profile_url = fields.Char(string='URL del perfil')
    active = fields.Boolean(default=True, tracking=True)
    demo_account = fields.Boolean(string='Cuenta demo', default=False, readonly=True)
    connection_state = fields.Selection([
        ('pending', 'Pendiente de conexión'),
        ('connected', 'Conectada'),
        ('error', 'Con error'),
    ], string='Estado de conexión', default='pending', tracking=True)
    follower_count = fields.Integer(string='Seguidores actuales', default=0)
    last_sync_at = fields.Datetime(string='Última sincronización', readonly=True)
    sync_message = fields.Char(string='Estado de sincronización', readonly=True)
    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True,
        default=lambda self: self.env.company, index=True)
    publication_ids = fields.One2many(
        'marketing.social.publication', 'account_id', string='Publicaciones')
    publication_count = fields.Integer(compute='_compute_counts', string='Número de publicaciones')
    interaction_count = fields.Integer(compute='_compute_counts', string='Interacciones')
    conversation_ids = fields.One2many(
        'marketing.social.conversation', 'account_id', string='Conversaciones')
    conversation_count = fields.Integer(compute='_compute_counts', string='Número de conversaciones')

    @api.depends('publication_ids', 'publication_ids.interaction_ids', 'conversation_ids')
    def _compute_counts(self):
        for record in self:
            record.publication_count = len(record.publication_ids)
            record.interaction_count = sum(len(item.interaction_ids) for item in record.publication_ids)
            record.conversation_count = len(record.conversation_ids)

    @api.constrains('external_id', 'platform')
    def _check_external_id_unique(self):
        records = self.filtered('external_id')
        if not records:
            return
        # Una consulta para todo el lote en vez de un search_count por
        # cuenta. La restriccion se dispara en cada alta o modificacion
        # masiva, que es justo cuando mas cuentas hay en juego.
        candidates = self.search([
            ('platform', 'in', records.mapped('platform')),
            ('external_id', 'in', records.mapped('external_id')),
            ('company_id', 'in', records.company_id.ids),
        ])
        seen = {}
        for candidate in candidates:
            key = (candidate.platform, candidate.external_id,
                   candidate.company_id.id)
            seen.setdefault(key, candidate.browse())
            seen[key] |= candidate
        for record in records:
            key = (record.platform, record.external_id, record.company_id.id)
            if len(seen.get(key, record.browse())) > 1:
                raise ValidationError(_('El identificador externo ya existe para esta red y compañía.'))

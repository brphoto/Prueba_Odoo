from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .marketing_social_constants import PLATFORM_SELECTION


class MarketingSocialAccount(models.Model):
    _name = 'marketing.social.account'
    _description = 'Cuenta de red social'
    _inherit = ['mail.thread', 'mail.activity.mixin']
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
    publication_count = fields.Integer(compute='_compute_counts', string='Publicaciones')
    interaction_count = fields.Integer(compute='_compute_counts', string='Interacciones')

    @api.depends('publication_ids', 'publication_ids.interaction_ids')
    def _compute_counts(self):
        for record in self:
            record.publication_count = len(record.publication_ids)
            record.interaction_count = sum(len(item.interaction_ids) for item in record.publication_ids)

    @api.constrains('external_id', 'platform')
    def _check_external_id_unique(self):
        for record in self.filtered('external_id'):
            duplicate = self.search_count([
                ('id', '!=', record.id),
                ('platform', '=', record.platform),
                ('external_id', '=', record.external_id),
                ('company_id', '=', record.company_id.id),
            ])
            if duplicate:
                raise ValidationError(_('El identificador externo ya existe para esta red y compañía.'))

from odoo import fields, models


class MarketingSocialNetworkSyncLog(models.Model):
    _name = 'marketing.social.network.sync.log'
    _description = 'Ejecución de sincronización social'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'started_at desc, id desc'

    name = fields.Char(string='Ejecución', required=True, tracking=True)
    connection_id = fields.Many2one(
        'marketing.social.network.connection', string='Conexión', required=True,
        ondelete='cascade', index=True)
    profile_id = fields.Many2one(
        'marketing.social.network.profile', string='Cuenta', ondelete='set null', index=True)
    platform = fields.Selection(related='connection_id.platform', store=True, index=True)
    company_id = fields.Many2one(related='connection_id.company_id', store=True, index=True)
    started_at = fields.Datetime(string='Inicio', required=True, default=fields.Datetime.now, index=True)
    finished_at = fields.Datetime(string='Fin', readonly=True)
    state = fields.Selection([
        ('running', 'En curso'), ('success', 'Correcta'),
        ('partial', 'Parcial'), ('error', 'Con error'),
    ], string='Resultado', required=True, default='running', tracking=True)
    duration_seconds = fields.Float(string='Duración (s)', readonly=True)
    publications_count = fields.Integer(string='Publicaciones', readonly=True)
    interactions_count = fields.Integer(string='Interacciones', readonly=True)
    error_message = fields.Text(string='Detalle del error', readonly=True)


from odoo import fields, models


class MarketingSocialCampaign(models.Model):
    _name = 'marketing.social.campaign'
    _description = 'Campaña de marketing social'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_start desc, name'

    name = fields.Char(string='Nombre de campaña', required=True, tracking=True)
    code = fields.Char(string='Código')
    objective = fields.Selection([
        ('awareness', 'Reconocimiento'),
        ('engagement', 'Interacción'),
        ('leads', 'Generación de oportunidades'),
        ('sales', 'Ventas'),
    ], string='Objetivo', default='engagement', tracking=True)
    date_start = fields.Date(string='Inicio')
    date_end = fields.Date(string='Fin')
    active = fields.Boolean(default=True)
    notes = fields.Text(string='Notas estratégicas')
    publication_ids = fields.One2many(
        'marketing.social.publication', 'campaign_id', string='Publicaciones')
    publication_count = fields.Integer(compute='_compute_counts', string='Publicaciones')
    interaction_count = fields.Integer(compute='_compute_counts', string='Interacciones')
    reach_total = fields.Integer(compute='_compute_counts', string='Alcance')
    engagement_rate = fields.Float(compute='_compute_counts', string='Engagement (%)')
    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True,
        default=lambda self: self.env.company, index=True)

    def _compute_counts(self):
        for record in self:
            publications = record.publication_ids
            metrics = publications.mapped('metric_ids')
            latest = self.env['marketing.social.metric.snapshot']
            for publication in publications:
                candidates = publication.metric_ids.sorted('snapshot_date')
                if candidates:
                    latest |= candidates[-1]
            record.publication_count = len(publications)
            record.interaction_count = sum(latest.mapped('total_interactions'))
            record.reach_total = sum(latest.mapped('reach'))
            total_reach = sum(latest.mapped('reach'))
            record.engagement_rate = (
                sum(latest.mapped('total_interactions')) / total_reach * 100
                if total_reach else 0.0
            )

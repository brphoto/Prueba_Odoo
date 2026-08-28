from odoo import _, fields, models


class MarketingSocialAlert(models.Model):
    _name = 'marketing.social.alert'
    _description = 'Alerta de marketing social'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'state, severity desc, detected_at desc, id desc'

    dashboard_id = fields.Many2one(
        'marketing.social.dashboard', string='Centro de mando', required=True,
        ondelete='cascade', index=True)
    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True, index=True)
    alert_type = fields.Selection([
        ('no_data', 'Sin datos'), ('low_engagement', 'Engagement bajo'),
        ('pending_comments', 'Comentarios pendientes'),
    ], string='Tipo', required=True, index=True)
    severity = fields.Selection([
        ('info', 'Informativa'), ('warning', 'Advertencia'), ('critical', 'Crítica'),
    ], string='Severidad', required=True, default='info', tracking=True)
    title = fields.Char(string='Alerta', required=True)
    details = fields.Text(string='Detalle')
    state = fields.Selection([
        ('open', 'Abierta'), ('resolved', 'Resuelta'),
    ], string='Estado', default='open', required=True, tracking=True)
    detected_at = fields.Datetime(string='Detectada', default=fields.Datetime.now, required=True)
    resolved_at = fields.Datetime(string='Resuelta el', readonly=True)

    def action_resolve(self):
        self.write({'state': 'resolved', 'resolved_at': fields.Datetime.now()})
        return True


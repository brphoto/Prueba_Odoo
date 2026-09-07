from odoo import _, api, fields, models


class MarketingSocialInteraction(models.Model):
    _name = 'marketing.social.interaction'
    _description = 'Interacción de red social'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'interaction_date desc, id desc'

    publication_id = fields.Many2one(
        'marketing.social.publication', string='Publicación', required=True,
        ondelete='cascade', index=True)
    account_id = fields.Many2one(
        'marketing.social.account', string='Cuenta', related='publication_id.account_id',
        store=True, index=True)
    platform = fields.Selection(
        related='publication_id.platform', store=True, string='Red')
    interaction_type = fields.Selection([
        ('comment', 'Comentario'), ('like', 'Me gusta'),
        ('share', 'Compartido'), ('save', 'Guardado'), ('mention', 'Mención'),
    ], string='Tipo', required=True, default='comment')
    author_name = fields.Char(string='Autor')
    external_id = fields.Char(string='ID externo', index=True)
    text = fields.Text(string='Contenido')
    interaction_date = fields.Datetime(string='Fecha', required=True)
    sentiment = fields.Selection([
        ('positive', 'Positivo'), ('neutral', 'Neutral'), ('negative', 'Negativo'),
    ], string='Sentimiento', default='neutral')
    intent = fields.Selection([
        ('question', 'Consulta'), ('price', 'Precio o cotización'),
        ('support', 'Soporte'), ('complaint', 'Queja'), ('praise', 'Reconocimiento'),
        ('other', 'Otro'),
    ], string='Intención', default='other')
    response_state = fields.Selection([
        ('pending', 'Pendiente'), ('responded', 'Respondida'), ('ignored', 'Ignorada'),
    ], string='Atención', default='pending', tracking=True)
    linked_note = fields.Char(string='Referencia de enlace opcional')
    company_id = fields.Many2one(
        'res.company', string='Compañía', related='publication_id.company_id', store=True, index=True)
    assigned_user_id = fields.Many2one('res.users', string='Responsable', tracking=True)

    _interaction_external_unique = models.Constraint(
        'unique(publication_id, external_id)',
        'La interacción externa ya existe para esta publicación.')

    def action_mark_responded(self):
        self.write({'response_state': 'responded'})
        return True

    def action_schedule_activity(self):
        Activity = self.env['mail.activity']
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        if not activity_type:
            return True
        for record in self:
            record.activity_schedule(
                activity_type_id=activity_type.id,
                user_id=record.assigned_user_id.id or self.env.uid,
                summary=_('Atender interacción social'),
                note=record.text or _('Revisar y responder esta interacción.'),
            )
        return True

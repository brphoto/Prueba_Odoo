from odoo import _, api, fields, models

class MarketingSocialConversation(models.Model):
    _name = 'marketing.social.conversation'
    _description = 'Conversación entrante de red social'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'last_message_at desc, id desc'

    name = fields.Char(string='Conversación', required=True, tracking=True)
    account_id = fields.Many2one(
        'marketing.social.account', string='Cuenta', required=True,
        ondelete='cascade', index=True, tracking=True)
    platform = fields.Selection(
        string='Red', related='account_id.platform', store=True, index=True)
    external_id = fields.Char(string='ID externo', required=True, index=True)
    contact_name = fields.Char(string='Contacto')
    contact_external_id = fields.Char(string='ID del contacto')
    last_message_at = fields.Datetime(string='Último mensaje', index=True)
    last_message_preview = fields.Text(string='Vista previa del último mensaje')
    message_count = fields.Integer(compute='_compute_message_stats', string='Mensajes')
    unread_count = fields.Integer(compute='_compute_message_stats', string='Sin leer')
    direction = fields.Selection([
        ('inbound', 'Entrante'), ('outbound', 'Saliente'), ('mixed', 'Mixta'),
    ], string='Dirección', compute='_compute_direction', store=True)
    state = fields.Selection([
        ('open', 'Abierta'), ('closed', 'Cerrada'), ('ignored', 'Ignorada'),
    ], string='Estado', default='open', tracking=True)
    url = fields.Char(string='Enlace externo')
    message_ids = fields.One2many(
        'marketing.social.conversation.message', 'conversation_id', string='Mensajes')
    company_id = fields.Many2one(
        'res.company', string='Compañía', related='account_id.company_id', store=True, index=True)

    _conversation_external_unique = models.Constraint(
        'unique(account_id, external_id)',
        'La conversación externa ya existe para esta cuenta.')

    @api.depends('message_ids', 'message_ids.read_state')
    def _compute_message_stats(self):
        for record in self:
            record.message_count = len(record.message_ids)
            record.unread_count = len(record.message_ids.filtered(
                lambda message: message.direction == 'inbound' and message.read_state == 'unread'))

    @api.depends('message_ids', 'message_ids.direction')
    def _compute_direction(self):
        for record in self:
            directions = set(record.message_ids.mapped('direction'))
            if directions == {'inbound'}:
                record.direction = 'inbound'
            elif directions == {'outbound'}:
                record.direction = 'outbound'
            elif directions:
                record.direction = 'mixed'
            else:
                record.direction = False

    def action_mark_read(self):
        self.mapped('message_ids').filtered(lambda message: message.direction == 'inbound').write({
            'read_state': 'read',
        })
        return True

    def action_schedule_activity(self):
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        if not activity_type:
            return True
        for record in self:
            record.activity_schedule(
                activity_type_id=activity_type.id,
                user_id=self.env.uid,
                summary=_('Revisar conversación social'),
                note=record.last_message_preview or _('Revisar y responder esta conversación.'),
            )
        return True


class MarketingSocialConversationMessage(models.Model):
    _name = 'marketing.social.conversation.message'
    _description = 'Mensaje de conversación social'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'message_at desc, id desc'

    conversation_id = fields.Many2one(
        'marketing.social.conversation', string='Conversación', required=True,
        ondelete='cascade', index=True)
    account_id = fields.Many2one(
        'marketing.social.account', string='Cuenta', related='conversation_id.account_id',
        store=True, index=True)
    platform = fields.Selection(
        string='Red', related='conversation_id.platform', store=True, index=True)
    external_id = fields.Char(string='ID externo', required=True, index=True)
    direction = fields.Selection([
        ('inbound', 'Entrante'), ('outbound', 'Saliente'),
    ], string='Dirección', required=True, default='inbound', index=True)
    author_name = fields.Char(string='Autor')
    author_external_id = fields.Char(string='ID del autor')
    body = fields.Text(string='Mensaje')
    message_at = fields.Datetime(string='Fecha', required=True, index=True)
    message_type = fields.Selection([
        ('text', 'Texto'), ('image', 'Imagen'), ('file', 'Archivo'), ('other', 'Otro'),
    ], string='Tipo', default='text')
    read_state = fields.Selection([
        ('unread', 'Sin leer'), ('read', 'Leído'),
    ], string='Lectura', default='unread', tracking=True)
    company_id = fields.Many2one(
        'res.company', string='Compañía', related='conversation_id.company_id', store=True, index=True)

    _message_external_unique = models.Constraint(
        'unique(conversation_id, external_id)',
        'El mensaje externo ya existe en esta conversación.')

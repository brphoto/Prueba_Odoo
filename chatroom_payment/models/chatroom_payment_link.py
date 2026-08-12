from odoo import _, fields, models


class ChatroomPaymentLink(models.Model):
    _name = 'chatroom.payment.link'
    _description = 'Enlace de pago enviado desde Chatroom'
    _order = 'create_date desc, id desc'

    name = fields.Char(string='Referencia', required=True, default=lambda self: _('Enlace de pago'))
    channel_id = fields.Many2one(
        'chatroom.channel', string='Conversacion', required=True,
        ondelete='cascade', index=True)
    partner_id = fields.Many2one(
        related='channel_id.partner_id', string='Cliente', store=True, index=True)
    res_model = fields.Char(string='Modelo', readonly=True)
    res_id = fields.Integer(string='ID del documento', readonly=True)
    document_name = fields.Char(string='Documento', readonly=True)
    provider_id = fields.Many2one(
        'payment.provider', string='Proveedor', ondelete='set null', index=True)
    transaction_id = fields.Many2one(
        'payment.transaction', string='Transaccion', ondelete='set null', index=True)
    amount = fields.Monetary(string='Importe', currency_field='currency_id', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Moneda', readonly=True)
    link = fields.Char(string='Enlace', required=True, copy=False, readonly=True)
    state = fields.Selection([
        ('generated', 'Generado'),
        ('sent', 'Enviado'),
        ('paid', 'Pagado'),
        ('expired', 'Expirado'),
        ('error', 'Error'),
    ], string='Estado', default='generated', required=True, index=True)
    sent_at = fields.Datetime(string='Enviado el', readonly=True)
    error_message = fields.Text(string='Detalle del error', readonly=True)


from odoo import _, api, fields, models
from odoo.exceptions import UserError


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
    synced_at = fields.Datetime(string='Sincronizado el', readonly=True, copy=False)
    resent_at = fields.Datetime(string='Reenviado el', readonly=True, copy=False)
    resent_by = fields.Many2one('res.users', string='Reenviado por', readonly=True, copy=False)
    error_message = fields.Text(string='Detalle del error', readonly=True)
    status_message = fields.Char(string='Resumen', compute='_compute_status_message')

    @api.depends('state', 'error_message')
    def _compute_status_message(self):
        for link in self:
            if link.state == 'paid':
                link.status_message = _('Pago confirmado correctamente.')
            elif link.state == 'expired':
                link.status_message = _('Enlace expirado; genera uno nuevo si el cliente desea pagar.')
            elif link.state == 'error':
                link.status_message = link.error_message or _('El proveedor reportó un error. Puedes diagnosticar o reenviar.')
            elif link.state == 'sent':
                link.status_message = _('Enviado; pendiente de confirmación del proveedor.')
            else:
                link.status_message = _('Generado; todavía no se ha enviado al cliente.')

    @api.model
    def _cron_sync_transaction_states(self):
        """Keep the Chatroom history aligned with the native payment state."""
        links = self.search([
            ('transaction_id', '!=', False),
            ('state', 'in', ('generated', 'sent')),
        ])
        now = fields.Datetime.now()
        for link in links:
            transaction = link.transaction_id
            values = {'synced_at': now}
            if transaction.state == 'done':
                values['state'] = 'paid'
            elif transaction.state in ('cancel', 'error'):
                values.update({
                    'state': 'error',
                    'error_message': transaction.state_message or _(
                        'La transacción de pago terminó en estado %s.') % transaction.state,
                })
            link.sudo().write(values)
        return True

    def action_resend(self):
        self.ensure_one()
        if self.state in ('paid', 'expired'):
            raise UserError(_('Este enlace ya no se puede reenviar porque está %s.') % self.state)
        if not self.link or not self.channel_id:
            raise UserError(_('El enlace no tiene una conversación válida.'))
        try:
            self.channel_id.action_send_text(_('Puedes pagar aquí: %s') % self.link)
        except Exception as error:
            self.write({'state': 'error', 'error_message': str(error)})
            raise
        self.write({
            'state': 'sent',
            'sent_at': fields.Datetime.now(),
            'resent_at': fields.Datetime.now(),
            'resent_by': self.env.user.id,
        })
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'title': _('Pago'), 'message': _('Enlace reenviado correctamente.'), 'type': 'success'},
        }

    def action_expire(self):
        self.ensure_one()
        if self.state == 'paid':
            raise UserError(_('No se puede expirar un enlace ya pagado.'))
        if self.transaction_id and self.transaction_id.state in ('pending', 'authorized'):
            self.transaction_id.sudo()._set_canceled(
                _('Enlace de pago expirado desde Chatroom.'))
        self.write({
            'state': 'expired',
            'error_message': _('Enlace expirado manualmente por %s.') % self.env.user.display_name,
            'synced_at': fields.Datetime.now(),
        })
        return True

    def action_sync_now(self):
        self.ensure_one()
        self._cron_sync_transaction_states()
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'title': _('Pago'), 'message': _('Estado sincronizado.'), 'type': 'success'},
        }

    def action_diagnose(self):
        self.ensure_one()
        transaction = self.transaction_id
        details = _('Sin transacción nativa asociada.')
        if transaction:
            details = _(
                'Proveedor: %(provider)s. Estado transacción: %(state)s. '
                'Mensaje: %(message)s.'
            ) % {
                'provider': transaction.provider_id.display_name,
                'state': transaction.state,
                'message': transaction.state_message or _('sin mensaje'),
            }
        self.write({'error_message': details, 'synced_at': fields.Datetime.now()})
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'title': _('Diagnóstico del pago'), 'message': details, 'type': 'info', 'sticky': True},
        }

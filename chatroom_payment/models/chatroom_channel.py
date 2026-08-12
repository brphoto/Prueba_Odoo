from odoo import _, fields, models
from odoo.exceptions import UserError


class ChatroomChannel(models.Model):
    _inherit = 'chatroom.channel'

    def _send_logged_payment_link(
            self, payment_link, res_model, res_id, provider=None,
            transaction=None):
        self.ensure_one()
        document = self.env[res_model].browse(res_id).exists()
        if not document:
            raise UserError(_('El documento ya no existe.'))
        values = {}
        if transaction:
            values = {
                'amount': transaction.amount,
                'currency_id': transaction.currency_id.id,
            }
        history = self.env['chatroom.payment.link'].sudo().create({
            'name': _('Enlace - %s') % document.display_name,
            'channel_id': self.id,
            'res_model': res_model,
            'res_id': document.id,
            'document_name': document.display_name,
            'provider_id': provider.id if provider else False,
            'transaction_id': transaction.id if transaction else False,
            'link': payment_link,
            **values,
        })
        try:
            result = self.action_send_text(_('Podes pagar aca: %s') % payment_link)
        except Exception as error:
            history.write({'state': 'error', 'error_message': str(error)})
            raise
        history.write({'state': 'sent', 'sent_at': fields.Datetime.now()})
        return result

    def action_send_payment_link(self, res_model, res_id):
        """Generate Odoo's generic payment link and send it through Chatroom.

        Provider-specific behavior belongs to connector modules such as
        ``chatroom_payment_payphone`` and can override this method.
        """
        self.ensure_one()
        if 'payment.link.wizard' not in self.env:
            raise UserError(_(
                'No se pudo generar el link de pago: el módulo de Pagos '
                'no está instalado.'))
        record = self.env[res_model].browse(res_id)
        if not record.exists():
            raise UserError(_('El documento ya no existe.'))
        try:
            wizard = self.env['payment.link.wizard'].with_context(
                active_model=res_model, active_id=res_id).create({})
        except AttributeError:
            raise UserError(_(
                'Este tipo de documento (%s) no soporta generar un link '
                'de pago en esta instalación de Odoo.') % res_model)
        if not wizard.link:
            raise UserError(_(
                'No se pudo generar el link de pago: revisá que haya un '
                'método de pago en línea configurado y que el documento '
                'tenga saldo pendiente.'))
        return self._send_logged_payment_link(wizard.link, res_model, res_id)

    def action_open_payment_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Enviar Link de Pago'),
            'res_model': 'chatroom.payment.link.wizard',
            'view_mode': 'form',
            # Las acciones devueltas por orm.call no pasan por
            # clean_action(); por eso Odoo necesita recibir views de forma
            # explícita antes de ejecutar actionService.doAction().
            'views': [(False, 'form')],
            'target': 'new',
            'context': {'default_channel_id': self.id},
        }

    def get_contact_panel_data(self):
        data = super().get_contact_panel_data()
        links = self.env['chatroom.payment.link'].sudo().search(
            [('channel_id', '=', self.id)], order='create_date desc', limit=5)
        data['payment_links'] = [{
            'id': link.id,
            'name': link.document_name or link.name,
            'link': link.link,
            'state': link.state,
            'provider_name': link.provider_id.name or _('Pago en linea'),
            'amount': link.amount,
            'currency_symbol': link.currency_id.symbol if link.currency_id else '',
            'create_date': fields.Datetime.to_string(link.create_date),
        } for link in links]
        return data

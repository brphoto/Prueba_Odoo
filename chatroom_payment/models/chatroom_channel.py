from odoo import _, models
from odoo.exceptions import UserError


class ChatroomChannel(models.Model):
    _inherit = 'chatroom.channel'

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
        return self.action_send_text(_('Podés pagar acá: %s') % wizard.link)

    def action_open_payment_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Enviar Link de Pago'),
            'res_model': 'chatroom.payment.link.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_channel_id': self.id},
        }

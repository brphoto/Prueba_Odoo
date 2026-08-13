from odoo import _, models


class ChatroomChannel(models.Model):
    _inherit = 'chatroom.channel'

    def action_send_payment_link(self, res_model, res_id):
        self.ensure_one()
        record = self.env[res_model].browse(res_id)
        if record.exists():
            company = record.company_id if 'company_id' in record._fields else self.env.company
            selected_id = self.env.context.get('chatroom_payment_provider_id')
            provider_domain = [
                ('code', '=', 'payphone'),
                ('payphone_flow', '=', 'link'),
                ('state', 'in', ('enabled', 'test')),
                ('company_id', '=', company.id),
            ]
            if selected_id:
                selected = self.env['payment.provider'].sudo().browse(selected_id).exists()
                if not selected or selected.code != 'payphone':
                    return super().action_send_payment_link(res_model, res_id)
                provider_domain = [('id', '=', selected.id)] + provider_domain[1:]
            provider = self.env['payment.provider'].sudo().search(
                provider_domain, order='sequence, id', limit=1)
            if provider:
                result = provider._chatroom_create_payment_link(record)
                if isinstance(result, dict):
                    payment_link = result.get('link')
                    transaction = result.get('transaction')
                else:
                    payment_link = result
                    transaction = False
                if not payment_link:
                    raise UserError(_('PayPhone no devolvió un enlace de pago.'))
                return self._send_logged_payment_link(
                    payment_link, res_model, res_id, provider, transaction)
        return super().action_send_payment_link(res_model, res_id)

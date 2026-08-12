from odoo import _, models


class ChatroomChannel(models.Model):
    _inherit = 'chatroom.channel'

    def action_send_payment_link(self, res_model, res_id):
        self.ensure_one()
        record = self.env[res_model].browse(res_id)
        if record.exists():
            provider = self.env['payment.provider'].sudo().search([
                ('code', '=', 'payphone'),
                ('payphone_flow', '=', 'link'),
                ('state', 'in', ('enabled', 'test')),
                ('company_id', '=', record.company_id.id if 'company_id' in record else self.env.company.id),
            ], order='sequence, id', limit=1)
            if provider:
                result = provider._chatroom_create_payment_link(record)
                if isinstance(result, dict):
                    payment_link = result['link']
                    transaction = result.get('transaction')
                else:
                    payment_link = result
                    transaction = False
                return self._send_logged_payment_link(
                    payment_link, res_model, res_id, provider, transaction)
        return super().action_send_payment_link(res_model, res_id)

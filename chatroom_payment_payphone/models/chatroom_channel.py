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
                payment_link = provider._chatroom_create_payment_link(record)
                return self.action_send_text(_('Podés pagar acá: %s') % payment_link)
        return super().action_send_payment_link(res_model, res_id)

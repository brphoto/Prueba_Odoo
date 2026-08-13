from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ChatroomPaymentLinkWizard(models.TransientModel):
    _name = 'chatroom.payment.link.wizard'
    _description = 'Enviar link de pago desde Chatroom'

    channel_id = fields.Many2one('chatroom.channel', required=True, readonly=True)
    sale_order_id = fields.Many2one(
        'sale.order', string='Presupuesto existente',
        domain="[('partner_id', '=', channel_partner_id), ('state', 'in', ('draft', 'sent', 'sale'))]"
    )
    channel_partner_id = fields.Many2one(related='channel_id.partner_id')
    provider_id = fields.Many2one(
        'payment.provider', string='Proveedor de pago',
        domain="[('state', 'in', ('enabled', 'test')), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        default=lambda self: self._default_provider(),
        help='Selecciona PayPhone para usar su API Link. Si lo dejas vacío, se usará el flujo estándar de Odoo.')
    company_id = fields.Many2one(related='channel_id.company_id', readonly=True)
    product_id = fields.Many2one('product.product', string='Producto nuevo')
    product_qty = fields.Float(string='Cantidad', default=1.0)

    @api.model
    def _default_provider(self):
        providers = self.env['payment.provider'].sudo().search([
            ('state', 'in', ('enabled', 'test')),
        ], order='sequence, id')
        return providers.filtered(lambda provider: provider.code == 'payphone')[:1].id or False

    def action_send(self):
        self.ensure_one()
        order = self.sale_order_id
        if not order:
            if not self.product_id:
                raise UserError(_('Selecciona un presupuesto existente o un producto.'))
            order = self.env['sale.order'].create({
                'partner_id': self.channel_id.partner_id.id,
                'origin': self.channel_id.display_name,
                'order_line': [(0, 0, {
                    'product_id': self.product_id.id,
                    'product_uom_qty': max(1.0, self.product_qty),
                })],
            })
        channel = self.channel_id
        if self.provider_id:
            channel = channel.with_context(chatroom_payment_provider_id=self.provider_id.id)
        channel.action_send_payment_link('sale.order', order.id)
        return {'type': 'ir.actions.act_window_close'}

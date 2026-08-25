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
    preview = fields.Text(string='Resumen del envío', compute='_compute_preview')
    readiness_message = fields.Char(string='Estado', compute='_compute_readiness')
    ready_to_send = fields.Boolean(compute='_compute_readiness')

    @api.depends('sale_order_id', 'product_id', 'product_qty', 'provider_id')
    def _compute_preview(self):
        for wizard in self:
            provider = wizard.provider_id.display_name if wizard.provider_id else _('Proveedor estándar de Odoo')
            if wizard.sale_order_id:
                wizard.preview = _('Pedido %s · Importe: %s · Proveedor: %s') % (
                    wizard.sale_order_id.name, wizard.sale_order_id.amount_total, provider)
            elif wizard.product_id:
                wizard.preview = _('Nuevo presupuesto · %s x %s · Proveedor: %s') % (
                    wizard.product_id.display_name, wizard.product_qty, provider)
            else:
                wizard.preview = _('Selecciona un presupuesto existente o un producto.')

    @api.depends('channel_id', 'sale_order_id', 'product_id', 'product_qty')
    def _compute_readiness(self):
        for wizard in self:
            wizard.ready_to_send = bool(
                wizard.channel_id and (wizard.sale_order_id or (wizard.product_id and wizard.product_qty > 0)))
            if not wizard.channel_id:
                wizard.readiness_message = _('Falta seleccionar la conversación.')
            elif wizard.channel_id.partner_id.whatsapp_opt_out:
                wizard.readiness_message = _('El cliente se dio de baja; primero debe volver a autorizar los mensajes.')
            elif not wizard.sale_order_id and not wizard.product_id:
                wizard.readiness_message = _('Selecciona un presupuesto existente o un producto.')
            elif not wizard.sale_order_id and wizard.product_qty <= 0:
                wizard.readiness_message = _('La cantidad del producto debe ser mayor que cero.')
            else:
                wizard.readiness_message = _('Listo para generar y enviar el enlace de pago.')

    @api.model
    def _default_provider(self):
        providers = self.env['payment.provider'].sudo().search([
            ('state', 'in', ('enabled', 'test')),
        ], order='sequence, id')
        return providers.filtered(lambda provider: provider.code == 'payphone')[:1].id or False

    def action_send(self):
        self.ensure_one()
        if self.channel_id.partner_id.whatsapp_opt_out:
            raise UserError(_("El cliente se dio de baja; primero debe volver a autorizar los mensajes."))
        order = self.sale_order_id
        if order and order.partner_id != self.channel_id.partner_id:
            raise UserError(_('El presupuesto seleccionado no pertenece al cliente de esta conversación.'))
        if not order:
            if not self.product_id:
                raise UserError(_('Selecciona un presupuesto existente o un producto.'))
            if self.product_qty <= 0:
                raise UserError(_('La cantidad del producto debe ser mayor que cero.'))
            order = self.env['sale.order'].create({
                'partner_id': self.channel_id.partner_id.id,
                'origin': self.channel_id.display_name,
                'order_line': [(0, 0, {
                    'product_id': self.product_id.id,
                    'product_uom_qty': self.product_qty,
                })],
            })
        channel = self.channel_id
        if self.provider_id:
            channel = channel.with_context(chatroom_payment_provider_id=self.provider_id.id)
        channel.action_send_payment_link('sale.order', order.id)
        return {'type': 'ir.actions.act_window_close'}

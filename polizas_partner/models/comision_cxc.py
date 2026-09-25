from odoo import models, fields, api, _
from odoo.exceptions import UserError

class ComisionCXC(models.Model):
    _name = 'comision.cxc'
    _description = 'Liquidación de Comisiones (CXC)'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        default=lambda self: 'LQ-CXC/%s' % self.env['ir.sequence'].next_by_code('comision.cxc'),
        readonly=True, copy=False, tracking=True
    )
    fecha = fields.Date(required=True, tracking=True)
    aseguradora_id = fields.Many2one(
        'polizas.aseguradoras', string="Aseguradora", required=True
    )
    poliza_ids = fields.One2many(
        'poliza.partner', 'comision_cxc_id',
        string="Pólizas Asociadas",
        domain="[('state', 'in', ['cobrado', 'pendiente'])]",
        tracking=True
    )
    total = fields.Float(compute='_compute_total', tracking=True)
    cantidad_polizas = fields.Integer("Nro. Pólizas", compute='_compute_total', store=False)
    sale_order_id = fields.Many2one('sale.order', string="Orden de Venta Generada", readonly=True)

    @api.depends('poliza_ids')
    def _compute_total(self):
        for rec in self:
            rec.total = sum(rec.poliza_ids.mapped('comision_broker_monto'))
            rec.cantidad_polizas = len(rec.poliza_ids)

    def action_generar_orden_venta(self):
        self.ensure_one()
        if not self.total:
            raise UserError("El valor total de la comisión es 0. No se puede generar la orden.")

        product_id = self.env['ir.config_parameter'].sudo().get_param('polizas.producto_comision_cxc_id')
        product = self.env['product.product'].browse(int(product_id)) if product_id else None

        if not product:
            raise UserError("No se ha configurado el producto para Comisión CXC en los ajustes del sistema.")

        partner = self.poliza_ids.mapped('partner_id')[:1]
        if not partner:
            raise UserError("No se puede determinar el cliente desde las pólizas seleccionadas.")

        sale_order = self.env['sale.order'].create({
            'partner_id': partner.id,
            'comision_cxc_id': self.id,
            'order_line': [(0, 0, {
                'product_id': product.id,
                'product_uom_qty': 1,
                'price_unit': self.total,
                'name': f'Comisión CXC - {self.name}',
            })]
        })

        self.sale_order_id = sale_order.id
        self.message_post(body=_("✅ Orden de Venta generada: <a href='#' data-oe-model='sale.order' data-oe-id='%s'>%s</a>") %
                               (sale_order.id, sale_order.name),
                          subtype_xmlid="mail.mt_note")

    def action_ver_orden_venta(self):
        self.ensure_one()
        if not self.sale_order_id:
            raise UserError("No hay una orden de venta generada para esta comisión.")

        return {
            'type': 'ir.actions.act_window',
            'name': 'Orden de Venta',
            'res_model': 'sale.order',
            'res_id': self.sale_order_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    comision_cxc_id = fields.Many2one('comision.cxc', string="Comisión CxC", readonly=True)

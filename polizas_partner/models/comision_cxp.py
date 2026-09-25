from odoo import models, fields, api, _
from odoo.exceptions import UserError

class ComisionCXP(models.Model):
    _name = 'comision.cxp'
    _description = 'Liquidación de Ejecutivos (CXP)'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        default=lambda self: 'LQ-CXP/%s' % self.env['ir.sequence'].next_by_code('comision.cxp'),
        readonly=True, copy=False, tracking=True
    )
    ejecutivo_id = fields.Many2one(
        'res.partner', string="Contacto",
        domain="[('is_company','=',False)]", tracking=True
    )
    executive_id = fields.Many2one(
        'polizas.ramos', string="Ejecutivo de Póliza", required=True, tracking=True
    )
    poliza_ids = fields.One2many(
        'poliza.partner', 'comision_cxp_id',
        string="Pólizas Asociadas",
        domain="[('state', 'in', ['cobrado', 'pendiente'])]",
        tracking=True
    )
    valor_total = fields.Float(compute='_compute_total', tracking=True)
    cantidad_polizas = fields.Integer("Nro. Pólizas", compute='_compute_total', store=False)
    fecha_pago = fields.Date(string="Fecha de Pago", tracking=True)
    purchase_order_id = fields.Many2one('purchase.order', string="Orden de Compra Generada", readonly=True)

    @api.depends('poliza_ids')
    def _compute_total(self):
        for rec in self:
            rec.valor_total = sum(rec.poliza_ids.mapped('comision_executivo_monto'))
            rec.cantidad_polizas = len(rec.poliza_ids)

    def action_generar_orden_compra(self):
        self.ensure_one()
        if not self.valor_total:
            raise UserError("El valor total de la comisión es 0. No se puede generar la orden.")

        product_id = self.env['ir.config_parameter'].sudo().get_param('polizas.producto_comision_cxp_id')
        product = self.env['product.product'].browse(int(product_id)) if product_id else None

        if not product:
            raise UserError("No se ha configurado el producto para Comisión CXP en los ajustes del sistema.")

        purchase_order = self.env['purchase.order'].create({
            'partner_id': self.executive_id.partner_id.id,
            'comision_cxp_id': self.id,
            'order_line': [(0, 0, {
                'product_id': product.id,
                'product_qty': 1,
                'price_unit': self.valor_total,
                'name': f'Comisión CXP - {self.name}',
                'product_uom_id': product.uom_id.id,
            })]
        })

        self.purchase_order_id = purchase_order.id
        self.message_post(body=_("✅ Orden de Compra generada: <a href='#' data-oe-model='purchase.order' data-oe-id='%s'>%s</a>") %
                               (purchase_order.id, purchase_order.name),
                          subtype_xmlid="mail.mt_note")

    def action_ver_orden_compra(self):
        self.ensure_one()
        if not self.purchase_order_id:
            raise UserError("No hay una orden de compra generada para esta comisión.")

        return {
            'type': 'ir.actions.act_window',
            'name': 'Orden de Compra',
            'res_model': 'purchase.order',
            'res_id': self.purchase_order_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    comision_cxp_id = fields.Many2one('comision.cxp', string="Comisión CxP", readonly=True)

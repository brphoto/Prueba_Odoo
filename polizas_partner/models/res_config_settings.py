from odoo import models, fields

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    producto_comision_cxc_id = fields.Many2one(
        'product.product',
        string="Producto Comisión CXC",
        config_parameter='polizas.producto_comision_cxc_id'
    )
    producto_comision_cxp_id = fields.Many2one(
        'product.product',
        string="Producto Comisión CXP",
        config_parameter='polizas.producto_comision_cxp_id'
    )
    days_reminder = fields.Integer(
        string="Días de Recordatorio",
        default=20,
        config_parameter='polizas.days_reminder'
    )

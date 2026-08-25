# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ChatroomSendCatalogWizard(models.TransientModel):
    _name = 'chatroom.send.catalog.wizard'
    _description = "Enviar catálogo de productos por WhatsApp"

    channel_id = fields.Many2one('chatroom.channel', required=True)
    product_ids = fields.Many2many(
        'product.product', string="Productos",
        domain=[('sale_ok', '=', True)],
        help="Hasta 10 productos: es el máximo que permite un mensaje de "
             "lista interactiva de WhatsApp.")
    preview = fields.Text(compute='_compute_preview')
    readiness_message = fields.Char(compute='_compute_readiness')
    ready_to_send = fields.Boolean(compute='_compute_readiness')

    @api.depends('channel_id', 'product_ids')
    def _compute_preview(self):
        for wizard in self:
            if wizard.product_ids:
                names = ', '.join(wizard.product_ids.mapped('display_name')[:5])
                if len(wizard.product_ids) > 5:
                    names += _(' y %s más') % (len(wizard.product_ids) - 5)
                wizard.preview = _('%s producto(s): %s') % (len(wizard.product_ids), names)
            else:
                wizard.preview = _('Selecciona los productos que aparecerán en el catálogo.')

    @api.depends('channel_id', 'product_ids')
    def _compute_readiness(self):
        for wizard in self:
            wizard.ready_to_send = bool(wizard.channel_id and 0 < len(wizard.product_ids) <= 10)
            if not wizard.channel_id:
                wizard.readiness_message = _('Falta seleccionar la conversación.')
            elif not wizard.product_ids:
                wizard.readiness_message = _('Selecciona al menos un producto.')
            elif len(wizard.product_ids) > 10:
                wizard.readiness_message = _('El catálogo permite como máximo 10 productos.')
            else:
                wizard.readiness_message = _('Listo para enviar el catálogo a esta conversación.')

    def action_send(self):
        self.ensure_one()
        if not self.channel_id:
            raise UserError(_("Selecciona la conversación de destino antes de enviar."))
        if not self.product_ids:
            raise UserError(_("Elegí al menos un producto."))
        if len(self.product_ids) > 10:
            raise UserError(_("Elegí como máximo 10 productos por mensaje."))
        self.channel_id.action_send_product_catalog(self.product_ids.ids)
        return {'type': 'ir.actions.act_window_close'}

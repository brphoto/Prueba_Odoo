# -*- coding: utf-8 -*-
from odoo import fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    ai_sales_last_notified_state = fields.Selection([
        ('assigned', 'Listo'),
        ('done', 'Entregado'),
        ('cancel', 'Cancelado'),
    ], string='Último estado notificado por Chatroom', copy=False)

    def _notify_ai_sales_state(self):
        Channel = self.env['chatroom.channel'].sudo()
        for picking in self:
            if picking.state not in ('assigned', 'done', 'cancel'):
                continue
            if picking.ai_sales_last_notified_state == picking.state:
                continue
            sale = picking.sale_id if 'sale_id' in picking._fields else self.env['sale.order'].browse()
            if not sale:
                continue
            channel = Channel.search([('ai_sales_last_order_id', '=', sale.id)], limit=1)
            if not channel:
                continue
            status = 'ready' if picking.state == 'assigned' else 'done' if picking.state == 'done' else 'cancelled'
            channel._fulfillment_notify_delivery(picking, status)
            picking.ai_sales_last_notified_state = picking.state

    def write(self, vals):
        result = super().write(vals)
        if 'state' in vals:
            self._notify_ai_sales_state()
        return result

    def action_assign(self):
        result = super().action_assign()
        self._notify_ai_sales_state()
        return result

    def action_cancel(self):
        result = super().action_cancel()
        self._notify_ai_sales_state()
        return result

    def _action_done(self, *args, **kwargs):
        result = super()._action_done(*args, **kwargs)
        self._notify_ai_sales_state()
        return result

# -*- coding: utf-8 -*-
from odoo import fields, models


class ChatroomAiSalesEvent(models.Model):
    _name = 'chatroom.ai.sales.event'
    _description = 'Auditoría de ventas autónomas de Chatroom'
    _order = 'create_date desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Nombre del evento', required=True, tracking=True)
    channel_id = fields.Many2one('chatroom.channel', string='Conversación', required=True, ondelete='cascade', index=True)
    partner_id = fields.Many2one(string='Cliente', related='channel_id.partner_id', store=True, readonly=True)
    order_id = fields.Many2one('sale.order', string='Pedido', ondelete='set null', index=True)
    event = fields.Selection([
        ('cart_updated', 'Carrito actualizado'),
        ('confirmation_requested', 'Confirmación solicitada'),
        ('quotation_created', 'Cotización creada'),
        ('order_confirmed', 'Pedido confirmado'),
        ('payment_link_sent', 'Link de pago enviado'),
        ('payment_received', 'Pago recibido'),
        ('invoice_created', 'Factura preparada'),
        ('post_sale_notified', 'Postventa notificada'),
        ('blocked', 'Bloqueado por política'),
        ('escalated', 'Escalado a humano'),
    ], string='Evento', required=True, index=True, tracking=True)
    amount = fields.Monetary(string='Importe', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string='Moneda', default=lambda self: self.env.company.currency_id)
    details = fields.Text(string='Detalle técnico')

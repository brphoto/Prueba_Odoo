# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ChatroomAiSandboxQuote(models.Model):
    _name = 'chatroom.ai.sandbox.quote'
    _description = 'Cotización generada por el laboratorio de IA'
    _order = 'id desc'
    _rec_name = 'name'

    name = fields.Char(string='Referencia', compute='_compute_name', store=True)
    sandbox_id = fields.Many2one(
        'chatroom.ai.sandbox', string='Laboratorio', required=True,
        ondelete='cascade', index=True)
    operation = fields.Selection([
        ('new', 'Nueva cotización'),
        ('append', 'Ampliación de cotización'),
    ], string='Operación', required=True, default='new')
    request_text = fields.Text(string='Solicitud del cliente', readonly=True)
    sale_order_id = fields.Many2one(
        'sale.order', string='Presupuesto nativo', readonly=True,
        ondelete='set null', index=True)
    sale_order_state = fields.Selection(
        related='sale_order_id.state', string='Estado del presupuesto', readonly=True)
    attachment_id = fields.Many2one(
        'ir.attachment', string='PDF estándar de Odoo', readonly=True,
        ondelete='set null')
    chat_message_id = fields.Many2one(
        'chatroom.message', string='Mensaje simulado', readonly=True,
        ondelete='set null')
    product_summary = fields.Text(string='Líneas generadas', readonly=True)
    detected_quantity = fields.Float(string='Cantidad detectada', readonly=True)
    # Snapshots are intentional: an append operation changes the native order
    # total, but the history must preserve what each operation produced.
    amount_untaxed = fields.Monetary(string='Subtotal', readonly=True)
    amount_total = fields.Monetary(string='Total', readonly=True)
    currency_id = fields.Many2one(
        'res.currency', string='Moneda', readonly=True)
    created_at = fields.Datetime(
        string='Generada el', related='create_date', readonly=True)

    @api.depends('operation', 'sale_order_id', 'sandbox_id')
    def _compute_name(self):
        for record in self:
            prefix = 'Ampliación' if record.operation == 'append' else 'Nueva'
            order_name = record.sale_order_id.name or 'pendiente'
            record.name = '%s · %s' % (prefix, order_name)

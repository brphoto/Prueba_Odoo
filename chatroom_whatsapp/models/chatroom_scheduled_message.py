# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ChatroomScheduledMessage(models.Model):
    """Mensaje de texto que un agente dejó armado para salir más tarde
    (seguimiento, recordatorio de pago, etc.) en vez de mandarlo ya. Un
    cron los va enviando cuando se cumple la fecha; no soporta adjuntos
    ni plantillas todavía, solo texto simple."""
    _name = 'chatroom.scheduled.message'
    _description = "Mensaje programado de Chatroom"
    _order = 'scheduled_date asc'

    channel_id = fields.Many2one(
        'chatroom.channel', string="Conversación", required=True,
        ondelete='cascade', index=True)
    body = fields.Text(required=True)
    scheduled_date = fields.Datetime(required=True, index=True)
    state = fields.Selection(
        [('pending', "Pendiente"),
         ('sent', "Enviado"),
         ('failed', "Falló"),
         ('cancelled', "Cancelado")],
        default='pending', required=True, copy=False)
    error_message = fields.Char(copy=False)

    def action_cancel(self):
        for rec in self:
            if rec.state == 'pending':
                rec.state = 'cancelled'

    @api.model
    def _cron_send_scheduled_messages(self):
        due = self.search([
            ('state', '=', 'pending'),
            ('scheduled_date', '<=', fields.Datetime.now()),
        ], limit=100)
        for rec in due:
            try:
                rec.channel_id.action_send_text(rec.body)
                rec.state = 'sent'
            except UserError as exc:
                _logger.info(
                    "No se pudo enviar el mensaje programado %s: %s", rec.id, exc)
                rec.write({'state': 'failed', 'error_message': str(exc)})

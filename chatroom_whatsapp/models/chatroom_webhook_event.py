# -*- coding: utf-8 -*-
import json
import logging

from odoo import api, fields, models

from ..controllers.whatsapp_webhook import WhatsAppWebhookController

_logger = logging.getLogger(__name__)


class ChatroomWebhookEvent(models.Model):
    _name = 'chatroom.whatsapp.webhook.event'
    _description = 'Evento pendiente del webhook de Chatroom'
    _order = 'create_date desc, id desc'

    name = fields.Char(required=True, index=True)
    object_type = fields.Char(string='Objeto externo', index=True)
    payload_json = fields.Text(string='Payload', required=True, copy=False)
    state = fields.Selection([
        ('pending', 'Pendiente'), ('running', 'Procesando'),
        ('done', 'Procesado'), ('failed', 'Fallido'),
    ], default='pending', required=True, index=True)
    attempts = fields.Integer(default=0, required=True, copy=False)
    max_attempts = fields.Integer(default=5, required=True, copy=False)
    next_attempt_at = fields.Datetime(default=fields.Datetime.now, required=True, index=True)
    processed_at = fields.Datetime(readonly=True, copy=False)
    error_message = fields.Text(readonly=True, copy=False)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company, index=True)

    @api.model
    def _cron_process_pending(self, limit=20):
        """Procesa eventos fuera de la petición HTTP pública."""
        now = fields.Datetime.now()
        self.env.cr.execute(
            """
            SELECT id
              FROM chatroom_whatsapp_webhook_event
             WHERE state = 'pending'
               AND next_attempt_at <= %s
             ORDER BY id
             FOR UPDATE SKIP LOCKED
             LIMIT %s
            """,
            (now, max(1, min(int(limit or 20), 100))),
        )
        events = self.browse([row[0] for row in self.env.cr.fetchall()]).exists()
        for event in events:
            event.write({
                'state': 'running',
                'attempts': event.attempts + 1,
                'error_message': False,
            })
            try:
                with self.env.cr.savepoint():
                    payload = json.loads(event.payload_json or '{}')
                    if not isinstance(payload, dict):
                        raise ValueError('El payload del webhook no es un objeto JSON.')
                    WhatsAppWebhookController().process_payload(
                        self.env(su=True), payload)
                event.write({
                    'state': 'done',
                    'processed_at': fields.Datetime.now(),
                    'error_message': False,
                    'payload_json': '{}',
                })
            except Exception as error:  # noqa: BLE001 - se persiste para reintentar
                _logger.exception(
                    'Falló el procesamiento del evento de webhook %s', event.id)
                attempts = event.attempts
                terminal = attempts >= max(event.max_attempts, 1)
                delay = min(3600, 60 * (2 ** max(attempts - 1, 0)))
                event.write({
                    'state': 'failed' if terminal else 'pending',
                    'next_attempt_at': fields.Datetime.add(now, seconds=delay),
                    'error_message': str(error)[:4000],
                })
        return len(events)

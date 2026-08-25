# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class ChatroomScheduledMessage(models.Model):
    """Mensaje que un agente dejó armado para salir más tarde (seguimiento,
    recordatorio de pago, etc.) o que un envío masivo encoló para no
    bloquear el request web con decenas/cientos de llamadas seguidas a la
    Cloud API de Meta. Un cron los va enviando de a lotes cuando se
    cumple la fecha; no soporta adjuntos todavía, solo texto y plantillas."""
    _name = 'chatroom.scheduled.message'
    _description = "Mensaje programado de Chatroom"
    _order = 'scheduled_date asc'

    channel_id = fields.Many2one(
        'chatroom.channel', string="Conversación", required=True,
        ondelete='cascade', index=True)
    message_type = fields.Selection(
        [('text', "Texto"), ('template', "Plantilla")],
        default='text', required=True)
    body = fields.Text(help="Texto a enviar, si el tipo es 'Texto'.")
    template_id = fields.Many2one(
        'chatroom.template', string="Plantilla", ondelete='restrict',
        help="Plantilla a enviar, si el tipo es 'Plantilla'. Las variables "
             "se resuelven al momento del envío con el mapeo configurado "
             "en la plantilla, igual que en las campañas.")
    scheduled_date = fields.Datetime(required=True, index=True)
    state = fields.Selection(
        [('pending', "Pendiente"),
         ('sent', "Enviado"),
         ('failed', "Falló"),
         ('cancelled', "Cancelado")],
        default='pending', required=True, copy=False)
    error_message = fields.Char(copy=False)
    preview = fields.Text(string='Vista previa', compute='_compute_preview')
    readiness_message = fields.Char(string='Estado de configuración', compute='_compute_readiness')

    @api.depends('message_type', 'body', 'template_id', 'template_id.body', 'template_id.preview_body')
    def _compute_preview(self):
        for rec in self:
            if rec.message_type == 'template':
                rec.preview = rec.template_id.preview_body if rec.template_id else _('Selecciona una plantilla aprobada.')
            else:
                rec.preview = rec.body or _('Escribe el mensaje que se enviará.')

    @api.depends('channel_id', 'message_type', 'body', 'template_id', 'scheduled_date')
    def _compute_readiness(self):
        now = fields.Datetime.now()
        for rec in self:
            if not rec.channel_id:
                rec.readiness_message = _('Falta seleccionar la conversación.')
            elif rec.channel_id.partner_id.whatsapp_opt_out:
                rec.readiness_message = _('El cliente se dio de baja; primero debe volver a autorizar los mensajes.')
            elif not rec.scheduled_date or rec.scheduled_date <= now:
                rec.readiness_message = _('La fecha debe ser posterior a la hora actual.')
            elif rec.message_type == 'text' and not (rec.body or '').strip():
                rec.readiness_message = _('Falta escribir el mensaje.')
            elif rec.message_type == 'template' and not rec.template_id:
                rec.readiness_message = _('Falta seleccionar una plantilla aprobada.')
            elif rec.message_type == 'template' and rec.template_id.status != 'approved':
                rec.readiness_message = _('La plantilla seleccionada aún no está aprobada.')
            else:
                rec.readiness_message = _('Listo para programar el envío.')

    @api.onchange('message_type')
    def _onchange_message_type(self):
        if self.message_type == 'text':
            self.template_id = False
        else:
            self.body = False

    @api.constrains('message_type', 'body', 'template_id')
    def _check_message_content(self):
        for rec in self:
            if rec.message_type == 'text' and not rec.body:
                raise ValidationError(_("Un mensaje programado de texto necesita el cuerpo del mensaje."))
            if rec.message_type == 'template' and not rec.template_id:
                raise ValidationError(_("Un mensaje programado de plantilla necesita elegir una plantilla."))

    def action_cancel(self):
        for rec in self:
            if rec.state == 'pending':
                rec.state = 'cancelled'

    def action_retry(self):
        """Reencola un mensaje fallido para el siguiente ciclo del cron."""
        failed = self.filtered(lambda rec: rec.state == 'failed')
        if not failed:
            raise UserError(_('Solo se pueden reintentar mensajes fallidos.'))
        failed.write({
            'state': 'pending',
            'scheduled_date': fields.Datetime.now(),
            'error_message': False,
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Mensaje programado'),
                'message': _('Se reencolaron %s mensaje(s) para el próximo ciclo.') % len(failed),
                'type': 'success',
            },
        }

    def _send(self):
        self.ensure_one()
        if self.message_type == 'template':
            self.channel_id.action_send_template(
                self.template_id.name, self.template_id.language,
                self.template_id.get_variable_values(self.channel_id))
        else:
            self.channel_id.action_send_text(self.body)

    @api.model
    def _cron_send_scheduled_messages(self):
        due = self.search([
            ('state', '=', 'pending'),
            ('scheduled_date', '<=', fields.Datetime.now()),
        ], limit=100)
        consecutive_failures = 0
        for rec in due:
            try:
                rec._send()
                rec.state = 'sent'
                consecutive_failures = 0
            except UserError as exc:
                _logger.info(
                    "No se pudo enviar el mensaje programado %s: %s", rec.id, exc)
                rec.write({'state': 'failed', 'error_message': str(exc)})
                consecutive_failures += 1
                if consecutive_failures >= 5:
                    # 5 fallos seguidos casi siempre significa credenciales
                    # vencidas o la Cloud API caída, no un problema de cada
                    # mensaje puntual: seguir insistiendo con los ~95
                    # restantes solo demora la corrida sin lograr nada. Se
                    # cortan acá y quedan 'pending' para el próximo cron (5
                    # minutos después), no 'failed' como los que sí se
                    # intentaron.
                    _logger.warning(
                        "Se cortó el envío de mensajes programados tras %s fallos "
                        "seguidos (posible caída de la Cloud API o credenciales "
                        "vencidas); el resto queda pendiente para el próximo cron.",
                        consecutive_failures)
                    break

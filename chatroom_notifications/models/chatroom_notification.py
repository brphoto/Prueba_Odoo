# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ChatroomNotification(models.Model):
    _name = 'chatroom.notification'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Notificación operativa de Chatroom'
    _order = 'priority desc, create_date desc, id desc'

    name = fields.Char(string='Título', required=True)
    message = fields.Text(string='Detalle', required=True)
    company_id = fields.Many2one(
        'res.company', string='Empresa', required=True,
        default=lambda self: self.env.company, index=True)
    notification_type = fields.Selection([
        ('sla', 'SLA'), ('integration', 'Integración'), ('payment', 'Pago'),
        ('ai', 'IA'), ('followup', 'Seguimiento'), ('other', 'Otra'),
    ], string='Tipo', required=True, default='other', index=True)
    priority = fields.Selection([
        ('0', 'Normal'), ('1', 'Importante'), ('2', 'Urgente'),
    ], string='Prioridad', required=True, default='0', index=True)
    state = fields.Selection([
        ('unread', 'No leída'), ('read', 'Leída'), ('snoozed', 'Pospuesta'),
        ('done', 'Resuelta'),
    ], string='Estado', required=True, default='unread', index=True)
    user_id = fields.Many2one('res.users', string='Destinatario', index=True)
    channel_id = fields.Many2one('chatroom.channel', string='Conversación', ondelete='cascade')
    partner_id = fields.Many2one('res.partner', string='Cliente', ondelete='set null')
    res_model = fields.Char(string='Modelo relacionado')
    res_id = fields.Integer(string='Registro relacionado')
    dedupe_key = fields.Char(string='Clave de deduplicación', index=True, copy=False)
    read_at = fields.Datetime(string='Leída el', readonly=True)
    snoozed_until = fields.Datetime(string='Pospuesta hasta', readonly=True)
    resolved_at = fields.Datetime(string='Resuelta el', readonly=True)
    escalation_level = fields.Integer(string='Nivel de escalamiento', default=0, copy=False)
    delivery_mode = fields.Selection([
        ('internal', 'Solo aviso interno'),
        ('email', 'Correo electrónico'),
        ('whatsapp', 'WhatsApp'),
        ('email_whatsapp', 'Correo y WhatsApp'),
    ], string='Entrega externa', default='internal', required=True, tracking=True,
        help='La entrega externa siempre se ejecuta con el botón Enviar aviso. Las tareas automáticas nunca envían sin revisión.')
    delivery_state = fields.Selection([
        ('pending', 'Pendiente'), ('sent', 'Enviado'), ('partial', 'Parcial'),
        ('skipped', 'No disponible'), ('failed', 'Fallido'),
    ], string='Estado de entrega', default='pending', readonly=True, copy=False)
    email_sent_at = fields.Datetime(string='Correo enviado el', readonly=True, copy=False)
    whatsapp_sent_at = fields.Datetime(string='WhatsApp enviado el', readonly=True, copy=False)
    delivery_error = fields.Text(string='Detalle de entrega', readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('channel_id') and not vals.get('company_id'):
                channel = self.env['chatroom.channel'].sudo().browse(
                    vals['channel_id']).exists()
                if channel and channel.company_id:
                    vals['company_id'] = channel.company_id.id
        return super().create(vals_list)

    @api.model
    def create_deduplicated(self, vals):
        key = vals.get('dedupe_key')
        if key:
            company_id = vals.get('company_id') or self.env.company.id
            existing = self.search([
                ('dedupe_key', '=', key), ('company_id', '=', company_id),
                ('state', '!=', 'done'),
            ], limit=1)
            if existing:
                existing.write({
                    'message': vals.get('message', existing.message),
                    'priority': vals.get('priority', existing.priority),
                })
                return existing
        return self.create(vals)

    def action_mark_read(self):
        self.write({'state': 'read', 'read_at': fields.Datetime.now()})
        return self._action_feedback(_('Notificaciones actualizadas'), _('%s marcada(s) como leída(s).') % len(self))

    def action_snooze(self):
        self.write({
            'state': 'snoozed',
            'snoozed_until': fields.Datetime.now() + timedelta(hours=1),
        })
        return self._action_feedback(_('Notificaciones pospuestas'), _('%s notificacion(es) pospuesta(s) por una hora.') % len(self))

    def action_resolve(self):
        self.write({'state': 'done', 'resolved_at': fields.Datetime.now()})
        return self._action_feedback(_('Notificaciones resueltas'), _('%s notificacion(es) resuelta(s).') % len(self))

    def action_reopen(self):
        self.write({'state': 'unread', 'read_at': False, 'snoozed_until': False, 'resolved_at': False})
        return self._action_feedback(_('Notificaciones reabiertas'), _('%s notificacion(es) reabierta(s).') % len(self))

    @api.model
    def _action_feedback(self, title, message):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': title, 'message': message, 'type': 'success', 'sticky': False},
        }

    def action_open_record(self):
        self.ensure_one()
        if not self.res_model or not self.res_id or self.res_model not in self.env:
            raise UserError(_('Esta notificación no tiene un registro relacionado válido.'))
        record = self.env[self.res_model].browse(self.res_id).exists()
        if not record:
            raise UserError(_('El registro relacionado ya no existe.'))
        return {
            'type': 'ir.actions.act_window', 'name': record.display_name,
            'res_model': self.res_model, 'res_id': self.res_id,
            'views': [(False, 'form')], 'target': 'current',
        }

    def action_dispatch(self):
        """Deliver an alert through native mail and the existing Chatroom API.

        A cron creates and deduplicates alerts, while a user decides when an
        external message may leave Odoo.
        """
        for notification in self:
            errors = []
            sent = []
            values = {'delivery_error': False}
            recipient = notification.user_id.partner_id if notification.user_id else notification.partner_id
            if notification.delivery_mode in ('email', 'email_whatsapp'):
                if recipient and recipient.email:
                    try:
                        safe_message = (notification.message or notification.name).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br/>')
                        mail = self.env['mail.mail'].sudo().create({
                            'subject': notification.name,
                            'body_html': '<p>%s</p>' % safe_message,
                            'email_to': recipient.email,
                            'auto_delete': True,
                        })
                        mail.send()
                        values['email_sent_at'] = fields.Datetime.now()
                        sent.append('correo')
                    except Exception as error:  # noqa: BLE001 - conservar el resto de entregas
                        errors.append(_('Correo: %s') % str(error)[:300])
                else:
                    errors.append(_('No hay correo electrónico configurado.'))
            if notification.delivery_mode in ('whatsapp', 'email_whatsapp'):
                channel = notification.channel_id
                if channel and channel.channel_type == 'whatsapp':
                    try:
                        channel.action_send_text(notification.message or notification.name)
                        values['whatsapp_sent_at'] = fields.Datetime.now()
                        sent.append('WhatsApp')
                    except Exception as error:  # noqa: BLE001 - dejar la alerta visible para reintentar
                        errors.append(_('WhatsApp: %s') % str(error)[:300])
                else:
                    errors.append(_('La alerta no tiene una conversación WhatsApp válida.'))
            if notification.delivery_mode == 'internal':
                values.update({'delivery_state': 'skipped', 'delivery_error': _('Configurada solo para aviso interno.')})
            elif sent and errors:
                values.update({'delivery_state': 'partial', 'delivery_error': '\n'.join(errors)})
            elif sent:
                values.update({'delivery_state': 'sent', 'delivery_error': False})
            else:
                values.update({'delivery_state': 'failed', 'delivery_error': '\n'.join(errors)})
            notification.write(values)
            notification.message_post(body=_('Entrega procesada: %s.') % (', '.join(sent) or _('sin entregas')))
        return self._action_feedback(_('Entrega procesada'), _('%s alerta(s) procesada(s).') % len(self))

    @api.model
    def _cron_create_sla_notifications(self):
        if 'chatroom.channel' not in self.env:
            return 0
        candidates = self.env['chatroom.channel'].sudo().search([
            ('state', 'in', ('open', 'pending')),
            ('assigned_user_id', '!=', False),
        ])
        channels = candidates.filtered(
            lambda c: c.first_response_sla_state in ('yellow', 'red'))
        created = 0
        for channel in channels:
            level = 2 if channel.first_response_sla_state == 'red' else 1
            key = 'sla:%s:%s' % (channel.id, channel.first_response_sla_state)
            notification = self.sudo().create_deduplicated({
                'name': _('SLA vencido' if level == 2 else 'SLA próximo a vencer'),
                'message': _('La conversación %s requiere atención del agente.') % channel.display_name,
                'notification_type': 'sla',
                'priority': str(level),
                'user_id': channel.assigned_user_id.id,
                'channel_id': channel.id,
                'partner_id': channel.partner_id.id,
                'res_model': 'chatroom.channel', 'res_id': channel.id,
                'dedupe_key': key, 'escalation_level': level,
                'company_id': channel.company_id.id,
            })
            created += bool(notification)
        return created

    @api.model
    def _cron_reopen_snoozed(self):
        due = self.search([('state', '=', 'snoozed'), ('snoozed_until', '<=', fields.Datetime.now())])
        due.write({'state': 'unread', 'snoozed_until': False})
        return len(due)

# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ChatroomNotification(models.Model):
    _name = 'chatroom.notification'
    _description = 'Notificación operativa de Chatroom'
    _order = 'priority desc, create_date desc, id desc'

    name = fields.Char(string='Título', required=True)
    message = fields.Text(string='Detalle', required=True)
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

    @api.model
    def create_deduplicated(self, vals):
        key = vals.get('dedupe_key')
        if key:
            existing = self.search([('dedupe_key', '=', key), ('state', '!=', 'done')], limit=1)
            if existing:
                existing.write({
                    'message': vals.get('message', existing.message),
                    'priority': vals.get('priority', existing.priority),
                })
                return existing
        return self.create(vals)

    def action_mark_read(self):
        self.write({'state': 'read', 'read_at': fields.Datetime.now()})
        return True

    def action_snooze(self):
        self.write({
            'state': 'snoozed',
            'snoozed_until': fields.Datetime.now() + timedelta(hours=1),
        })
        return True

    def action_resolve(self):
        self.write({'state': 'done', 'resolved_at': fields.Datetime.now()})
        return True

    def action_reopen(self):
        self.write({'state': 'unread', 'read_at': False, 'snoozed_until': False, 'resolved_at': False})
        return True

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

    @api.model
    def _cron_create_sla_notifications(self):
        if 'chatroom.channel' not in self.env:
            return 0
        channels = self.env['chatroom.channel'].sudo().search([
            ('state', 'in', ('open', 'pending')),
            ('first_response_sla_state', 'in', ('yellow', 'red')),
            ('assigned_user_id', '!=', False),
        ])
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
            })
            created += bool(notification)
        return created

    @api.model
    def _cron_reopen_snoozed(self):
        due = self.search([('state', '=', 'snoozed'), ('snoozed_until', '<=', fields.Datetime.now())])
        due.write({'state': 'unread', 'snoozed_until': False})
        return len(due)

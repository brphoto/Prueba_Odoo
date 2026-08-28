# -*- coding: utf-8 -*-
import json
import logging
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class CrmEngagementExecution(models.Model):
    _name = 'crm.engagement.execution'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Ejecución de automatización comercial'
    _order = 'scheduled_date desc, id desc'

    automation_id = fields.Many2one(
        'crm.engagement.automation', required=True, ondelete='cascade', index=True)
    step_id = fields.Many2one(
        'crm.engagement.automation.step', required=True, ondelete='cascade')
    partner_id = fields.Many2one('res.partner', required=True, ondelete='cascade', index=True)
    event_key = fields.Char(required=True, index=True)
    event_name = fields.Char(string='Evento')
    event_date = fields.Date(string='Fecha del evento')
    scheduled_date = fields.Date(string='Fecha programada', required=True, index=True)
    channel = fields.Selection(related='step_id.channel', store=True)
    state = fields.Selection([
        ('queued', 'En cola'),
        ('pending_approval', 'Pendiente de aprobación'),
        ('sent', 'Ejecutada'),
        ('failed', 'Fallida'),
        ('cancelled', 'Cancelada'),
    ], default='queued', required=True, index=True)
    error_message = fields.Text(string='Detalle del error')
    context_json = fields.Text(string='Contexto de ejecución')
    sent_at = fields.Datetime(string='Ejecutada el', readonly=True)

    def action_open_partner(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': self.partner_id.display_name,
            'res_model': 'res.partner', 'res_id': self.partner_id.id,
            'view_mode': 'form', 'target': 'current',
        }

    _execution_unique = models.Constraint(
        'unique(automation_id, step_id, partner_id, event_key)',
        'Esta notificación ya fue programada para el cliente y evento.')

    @api.model
    def _render_message(self, template, context):
        text = template or ''
        def replace_token(match):
            return str(context.get(match.group(1), '') or '')
        text = re.sub(r'\$\{([a-zA-Z0-9_]+)\}', replace_token, text)
        return text

    def _activity_user(self, partner):
        return self.step_id.user_id or partner.user_id or self.env.user

    def _execute_activity(self, message, context):
        self.ensure_one()
        activity_type = self.step_id.activity_type_id or self.env['mail.activity.type'].search(
            [('category', '=', 'default')], order='sequence, id', limit=1)
        if not activity_type:
            raise UserError(_('No existe un tipo de actividad para programar el recordatorio.'))
        model_id = self.env['ir.model']._get_id('res.partner')
        self.env['mail.activity'].create({
            'activity_type_id': activity_type.id,
            'summary': self._render_message(self.step_id.activity_summary, context),
            'note': message,
            'date_deadline': fields.Date.context_today(self),
            'user_id': self._activity_user(self.partner_id).id,
            'res_model_id': model_id,
            'res_id': self.partner_id.id,
        })

    def _execute_notification(self, message):
        self.ensure_one()
        self.partner_id.message_post(
            body=message,
            message_type='notification',
            subtype_xmlid='mail.mt_note',
        )

    def _execute_email(self, message, context):
        self.ensure_one()
        template = self.step_id.mail_template_id
        if template:
            if template.model_id and template.model_id.model != 'res.partner':
                raise UserError(_('La plantilla de correo debe estar dirigida a Contactos.'))
            template.with_context(engagement_context=context).send_mail(
                self.partner_id.id, force_send=False)
            return
        if not self.partner_id.email:
            raise UserError(_('El cliente no tiene correo electrónico configurado.'))
        mail = self.env['mail.mail'].sudo().create({
            'subject': self._render_message(self.step_id.email_subject, context),
            'body_html': message,
            'email_to': self.partner_id.email,
            'auto_delete': True,
        })
        mail.send()

    def _execute_whatsapp(self, context):
        self.ensure_one()
        if 'chatroom.channel' not in self.env or 'chatroom.template' not in self.env:
            raise UserError(_('Instala Chatroom WhatsApp para utilizar recordatorios por WhatsApp.'))
        if not self.partner_id.phone:
            raise UserError(_('El cliente no tiene teléfono configurado.'))
        template = self.env['chatroom.template'].search([
            ('name', '=', self.step_id.whatsapp_template_name),
            ('language', '=', self.step_id.whatsapp_template_language or 'es'),
            ('status', '=', 'approved'),
        ], limit=1)
        if not template:
            raise UserError(_('No existe una plantilla aprobada de WhatsApp con ese nombre e idioma.'))
        channel_model = self.env['chatroom.channel']
        channel_id = channel_model.action_start_conversation(
            self.partner_id.id, phone=self.partner_id.phone)
        channel = channel_model.browse(channel_id)
        values = template.get_variable_values(channel)
        channel.action_send_template(template.name, template.language, values)

    def action_execute(self):
        sent = failed = skipped = 0
        for execution in self:
            if execution.state not in ('queued', 'pending_approval'):
                skipped += 1
                continue
            try:
                context = json.loads(execution.context_json or '{}')
                message = execution._render_message(execution.step_id.message_body, context)
                if execution.channel == 'activity':
                    execution._execute_activity(message, context)
                elif execution.channel == 'notification':
                    execution._execute_notification(message)
                elif execution.channel == 'email':
                    execution._execute_email(message, context)
                elif execution.channel == 'whatsapp':
                    execution._execute_whatsapp(context)
                execution.write({'state': 'sent', 'sent_at': fields.Datetime.now(), 'error_message': False})
                execution.message_post(body=_('Recordatorio ejecutado por el canal %s.') % execution.channel)
                sent += 1
            except Exception as exc:  # noqa: BLE001 - conservar el fallo en el historial
                _logger.exception('Falló la automatización comercial %s', execution.id)
                execution.write({'state': 'failed', 'error_message': str(exc)[:1000]})
                execution.message_post(body=_('Falló la ejecución: %s') % str(exc)[:500], message_type='notification')
                failed += 1
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Automatización procesada'),
                'message': _('%s ejecutadas, %s fallidas, %s omitidas.') % (
                    sent, failed, skipped),
                'type': 'success' if not failed else 'warning',
                'sticky': False,
            },
        }

    def action_approve(self):
        if not self.env.user.has_group('crm_engagement_automation.group_crm_engagement_manager'):
            raise UserError(_('Solo un administrador puede aprobar recordatorios.'))
        pending = self.filtered(lambda execution: execution.state == 'pending_approval')
        if not pending:
            raise UserError(_('Seleccione ejecuciones pendientes de aprobación.'))
        pending.write({'state': 'queued', 'error_message': False})
        return pending.action_execute()

    def action_retry(self):
        failed = self.filtered(lambda execution: execution.state == 'failed')
        if not failed:
            raise UserError(_('Seleccione ejecuciones fallidas para reintentar.'))
        failed.write({'state': 'queued', 'error_message': False})
        return failed.action_execute()

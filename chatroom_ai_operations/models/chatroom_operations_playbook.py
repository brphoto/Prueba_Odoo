# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ChatroomOperationsPlaybook(models.Model):
    _name = 'chatroom.operations.playbook'
    _description = 'Playbook de comunicación de Chatroom'
    _order = 'sequence, name'

    name = fields.Char(string='Nombre', required=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    trigger = fields.Selection([
        ('cart_abandoned', 'Carrito abandonado'),
        ('payment_failed', 'Pago fallido'),
        ('delivery_ready', 'Entrega preparada'),
        ('post_sale', 'Postventa'),
        ('birthday', 'Cumpleaños del cliente'),
        ('manual', 'Prueba manual'),
    ], string='Disparador', required=True, default='manual')
    template_id = fields.Many2one('chatroom.template', string='Plantilla WhatsApp')
    execution_mode = fields.Selection([
        ('notify', 'Solo avisar al equipo'),
        ('send_template', 'Enviar plantilla aprobada'),
    ], string='Modo de ejecución', required=True, default='notify')
    approval_required = fields.Boolean(string='Requiere aprobación humana', default=True)
    delay_hours = fields.Integer(string='Espera mínima (horas)', default=24)
    max_per_run = fields.Integer(string='Máximo por ejecución', default=20)
    test_channel_id = fields.Many2one('chatroom.channel', string='Conversación para probar')
    last_run_at = fields.Datetime(string='Última ejecución', readonly=True)
    last_result = fields.Char(string='Resultado', readonly=True)

    @api.constrains('execution_mode', 'template_id')
    def _check_template(self):
        for record in self:
            if record.execution_mode == 'send_template' and not record.template_id:
                raise ValidationError(_('Selecciona una plantilla para poder enviar mensajes.'))

    def _candidate_channels(self):
        Channel = self.env['chatroom.channel'].sudo()
        limit = max(1, min(self.max_per_run or 20, 100))
        cutoff = fields.Datetime.now() - timedelta(hours=max(0, self.delay_hours or 0))
        if self.trigger == 'manual':
            return self.test_channel_id if self.test_channel_id else Channel.browse()
        if self.trigger == 'cart_abandoned':
            channels = Channel.search([('state', 'in', ('open', 'pending')), ('cart_line_ids', '!=', False)], limit=limit * 3)
            return channels.filtered(lambda channel: (
                (max(channel.cart_line_ids.mapped('create_date')) if channel.cart_line_ids.mapped('create_date') else False)
                and max(channel.cart_line_ids.mapped('create_date')) <= cutoff
            ))[:limit]
        if self.trigger == 'payment_failed':
            return self.env['chatroom.payment.link'].sudo().search([
                ('state', '=', 'error'), ('create_date', '<=', cutoff),
            ], limit=limit).mapped('channel_id')[:limit]
        if self.trigger == 'delivery_ready':
            return Channel.search([('ai_sales_delivery_status', '=', 'ready')], limit=limit) if 'ai_sales_delivery_status' in Channel._fields else Channel.browse()
        if self.trigger == 'post_sale':
            return Channel.search([('ai_sales_status', '=', 'post_sale')], limit=limit) if 'ai_sales_status' in Channel._fields else Channel.browse()
        if self.trigger == 'birthday' and 'birthday' in self.env['res.partner']._fields:
            today = fields.Date.today()
            return Channel.search([('partner_id.birthday', '!=', False), ('partner_id.birthday', 'like', today.strftime('-%m-%d'))], limit=limit)
        return Channel.browse()

    def _notify(self, channel, message):
        if 'chatroom.notification' not in self.env:
            return
        self.env['chatroom.notification'].sudo().create_deduplicated({
            'name': _('Playbook: %s') % self.name,
            'message': message,
            'notification_type': 'followup',
            'priority': '1',
            'user_id': channel.assigned_user_id.id,
            'channel_id': channel.id,
            'partner_id': channel.partner_id.id,
            'res_model': 'chatroom.channel',
            'res_id': channel.id,
            'dedupe_key': 'playbook:%s:%s:%s' % (self.id, channel.id, fields.Date.today()),
        })

    def _execute_channel(self, channel):
        message = _('El playbook «%s» encontró una conversación que requiere seguimiento.') % self.name
        if self.approval_required or self.execution_mode == 'notify':
            self._notify(channel, message)
            return 'notificado'
        template = self.template_id
        if template.status != 'approved' or not template.waba_template_id:
            self._notify(channel, _('La plantilla del playbook no está aprobada en Meta; se requiere revisión.'))
            return 'bloqueado'
        try:
            values = template.get_variable_values(channel)
            channel.action_send_template(template.name, template.language, values)
            return 'enviado'
        except Exception as exc:  # noqa: BLE001 - un canal fallido no detiene los demás
            self._notify(channel, _('No se pudo enviar el playbook: %s') % exc)
            return 'error'

    def action_run_now(self):
        self.ensure_one()
        channels = self._candidate_channels()
        results = [self._execute_channel(channel) for channel in channels]
        self.write({'last_run_at': fields.Datetime.now(), 'last_result': _('%s canal(es): %s') % (len(results), ', '.join(results) or 'sin coincidencias')})
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'title': _('Playbook ejecutado'), 'message': self.last_result, 'type': 'success',
        }}

    @api.model
    def _cron_run_playbooks(self):
        total = 0
        for playbook in self.sudo().search([('active', '=', True)]):
            channels = playbook._candidate_channels()
            for channel in channels:
                playbook._execute_channel(channel)
                total += 1
            playbook.write({'last_run_at': fields.Datetime.now(), 'last_result': _('%s canal(es) procesado(s).') % len(channels)})
        return total

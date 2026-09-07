# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ChatroomOperationsPlaybook(models.Model):
    _name = 'chatroom.operations.playbook'
    _description = 'Playbook de comunicación de Chatroom'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, name'

    name = fields.Char(string='Nombre', required=True)
    active = fields.Boolean(string='Activo', default=True, tracking=True)
    sequence = fields.Integer(string='Orden', default=10)
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
    approval_required = fields.Boolean(string='Requiere aprobación humana', default=True, tracking=True)
    delay_hours = fields.Integer(string='Espera mínima (horas)', default=24)
    max_per_run = fields.Integer(string='Máximo por ejecución', default=20)
    test_channel_id = fields.Many2one('chatroom.channel', string='Conversación para probar')
    company_id = fields.Many2one(
        'res.company', string='Empresa', required=True,
        default=lambda self: self.env.company, index=True)
    last_run_at = fields.Datetime(string='Última ejecución', readonly=True)
    last_result = fields.Char(string='Resultado', readonly=True)
    last_processed_count = fields.Integer(string='Procesados en la última ejecución', readonly=True)
    last_notified_count = fields.Integer(string='Avisos internos en la última ejecución', readonly=True)
    last_sent_count = fields.Integer(string='Plantillas enviadas en la última ejecución', readonly=True)
    last_blocked_count = fields.Integer(string='Bloqueados en la última ejecución', readonly=True)
    last_error_count = fields.Integer(string='Errores en la última ejecución', readonly=True)
    run_ids = fields.One2many(
        'chatroom.operations.playbook.run', 'playbook_id',
        string='Historial de ejecuciones', readonly=True)
    run_count = fields.Integer(string='Ejecuciones', compute='_compute_run_count')

    def _compute_run_count(self):
        Run = self.env['chatroom.operations.playbook.run'].sudo()
        for record in self:
            record.run_count = Run.search_count([('playbook_id', '=', record.id)])

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
            return self.test_channel_id.filtered(lambda channel: channel.company_id == self.company_id) if self.test_channel_id else Channel.browse()
        if self.trigger == 'cart_abandoned':
            channels = Channel.search([('company_id', '=', self.company_id.id), ('state', 'in', ('open', 'pending')), ('cart_line_ids', '!=', False)], limit=limit * 3)
            return channels.filtered(lambda channel: (
                (max(channel.cart_line_ids.mapped('create_date')) if channel.cart_line_ids.mapped('create_date') else False)
                and max(channel.cart_line_ids.mapped('create_date')) <= cutoff
            ))[:limit]
        if self.trigger == 'payment_failed':
            return self.env['chatroom.payment.link'].sudo().search([
                ('channel_id.company_id', '=', self.company_id.id), ('state', '=', 'error'), ('create_date', '<=', cutoff),
            ], limit=limit).mapped('channel_id')[:limit]
        if self.trigger == 'delivery_ready':
            return Channel.search([('company_id', '=', self.company_id.id), ('ai_sales_delivery_status', '=', 'ready')], limit=limit) if 'ai_sales_delivery_status' in Channel._fields else Channel.browse()
        if self.trigger == 'post_sale':
            return Channel.search([('company_id', '=', self.company_id.id), ('ai_sales_status', '=', 'post_sale')], limit=limit) if 'ai_sales_status' in Channel._fields else Channel.browse()
        if self.trigger == 'birthday' and 'birthday' in self.env['res.partner']._fields:
            # `fields.Date.today()` es la fecha en UTC. En una zona atrasada
            # respecto de UTC (America, por ejemplo) despues de las 19:00
            # locales ya devuelve el dia siguiente: el playbook de cumpleanos
            # felicitaba un dia antes y no felicitaba el dia correcto.
            today = fields.Date.context_today(self)
            return Channel.search([('company_id', '=', self.company_id.id), ('partner_id.birthday', '!=', False), ('partner_id.birthday', 'like', today.strftime('-%m-%d'))], limit=limit)
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
            'dedupe_key': 'playbook:%s:%s:%s' % (self.id, channel.id, fields.Date.context_today(self)),
        })

    def _execute_channel(self, channel):
        message = _('El playbook «%s» encontró una conversación que requiere seguimiento.') % self.name
        if self.approval_required or self.execution_mode == 'notify':
            self._notify(channel, message)
            return 'notified'
        template = self.template_id
        if template.status != 'approved' or not template.waba_template_id:
            self._notify(channel, _('La plantilla del playbook no está aprobada en Meta; se requiere revisión.'))
            return 'blocked'
        try:
            values = template.get_variable_values(channel)
            channel.action_send_template(template.name, template.language, values)
            return 'sent'
        except Exception as exc:  # noqa: BLE001 - un canal fallido no detiene los demás
            self._notify(channel, _('No se pudo enviar el playbook: %s') % exc)
            return 'error'

    @staticmethod
    def _result_counts(results):
        return {
            'notified': results.count('notified'),
            'sent': results.count('sent'),
            'blocked': results.count('blocked'),
            'error': results.count('error'),
        }

    def _record_run(self, execution_type, channels, results):
        self.ensure_one()
        counts = self._result_counts(results)
        processed = len(channels)
        status = 'error' if counts['error'] == processed and processed else 'partial' if counts['error'] or counts['blocked'] else 'done'
        summary = _('%s procesado(s): %s aviso(s), %s enviado(s), %s bloqueado(s), %s error(es).') % (
            processed, counts['notified'], counts['sent'], counts['blocked'], counts['error'])
        run = self.env['chatroom.operations.playbook.run'].sudo().create({
            'playbook_id': self.id,
            'company_id': self.company_id.id,
            'execution_type': execution_type,
            'state': status,
            'channels_processed': processed,
            'notified_count': counts['notified'],
            'sent_count': counts['sent'],
            'blocked_count': counts['blocked'],
            'error_count': counts['error'],
            'summary': summary,
        })
        self.write({
            'last_run_at': run.execution_date,
            'last_result': summary,
            'last_processed_count': processed,
            'last_notified_count': counts['notified'],
            'last_sent_count': counts['sent'],
            'last_blocked_count': counts['blocked'],
            'last_error_count': counts['error'],
        })
        return run

    def action_view_runs(self):
        self.ensure_one()
        action = self.env.ref(
            'chatroom_ai_operations.action_chatroom_operations_playbook_run').read()[0]
        action.update({
            'name': _('Ejecuciones: %s') % self.name,
            'domain': [('playbook_id', '=', self.id)],
            'context': {'default_playbook_id': self.id},
        })
        return action

    def action_run_now(self):
        self.ensure_one()
        channels = self._candidate_channels()
        results = [self._execute_channel(channel) for channel in channels]
        self._record_run('manual', channels, results)
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'title': _('Playbook ejecutado'), 'message': self.last_result, 'type': 'success',
        }}

    @api.model
    def _cron_run_playbooks(self):
        total = 0
        for playbook in self.sudo().search([('active', '=', True)]):
            channels = playbook._candidate_channels()
            results = [playbook._execute_channel(channel) for channel in channels]
            playbook._record_run('cron', channels, results)
            total += len(channels)
        return total

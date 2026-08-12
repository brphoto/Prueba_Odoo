# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class ChatAutomationRule(models.Model):
    _name = 'chat.automation.rule'
    _description = 'Regla de automatización comercial del chat'
    _inherit = ['mail.thread']
    _order = 'sequence, id'

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    trigger = fields.Selection([
        ('stage_change', 'Cambio de etapa'),
        ('no_activity', 'Días sin actividad'),
        ('specific_date', 'Fecha específica'),
        ('tag_added', 'Etiqueta añadida'),
    ], string='Si', required=True, default='stage_change')
    stage_id = fields.Many2one('crm.stage', string='Etapa')
    days_without_activity = fields.Integer(default=3)
    specific_date = fields.Date()
    tag_id = fields.Many2one('crm.tag', string='Etiqueta')
    action = fields.Selection([
        ('whatsapp_message', 'Enviar mensaje de WhatsApp'),
        ('create_activity', 'Crear tarea interna'),
        ('change_user', 'Cambiar asignado'),
    ], string='Entonces', required=True, default='create_activity')
    template_id = fields.Many2one(
        'chatroom.template', string='Plantilla WhatsApp',
        domain=[('status', '=', 'approved')])
    message_body = fields.Text(string='Mensaje')
    activity_summary = fields.Char(string='Resumen de tarea')
    activity_days = fields.Integer(string='Vence en días', default=1)
    user_id = fields.Many2one('res.users', string='Nuevo asignado')
    last_run_date = fields.Date(copy=False, readonly=True)

    def _matches(self, lead, trigger):
        self.ensure_one()
        if not self.active or self.trigger != trigger:
            return False
        if self.trigger == 'stage_change':
            return not self.stage_id or lead.stage_id == self.stage_id
        if self.trigger == 'tag_added':
            return not self.tag_id or self.tag_id in lead.tag_ids
        if self.trigger == 'specific_date':
            return self.specific_date == fields.Date.context_today(self)
        if self.trigger == 'no_activity':
            last_date = max(filter(None, [lead.write_date, lead.date_last_stage_update]), default=False)
            return bool(last_date and fields.Datetime.now() >= fields.Datetime.add(
                last_date, days=self.days_without_activity))
        return False

    def _run_action(self, lead):
        self.ensure_one()
        if self.action == 'change_user':
            lead.write({'user_id': self.user_id.id, 'assignment_pool_status': 'assigned'})
            return
        if self.action == 'create_activity':
            activity_type = self.env['mail.activity.type'].search(
                [('category', '=', 'default')], order='sequence, id', limit=1)
            if activity_type:
                self.env['mail.activity'].create({
                    'activity_type_id': activity_type.id,
                    'summary': self.activity_summary or self.name,
                    'date_deadline': fields.Date.add(
                        fields.Date.context_today(self), days=max(0, self.activity_days)),
                    'user_id': lead.user_id.id or self.env.user.id,
                    'res_model_id': self.env['ir.model']._get_id('crm.lead'),
                    'res_id': lead.id,
                })
            return
        if self.action == 'whatsapp_message' and lead.partner_id:
            channels = self.env['chatroom.channel'].search([
                ('partner_id', '=', lead.partner_id.id),
                ('state', 'in', ('open', 'pending')),
            ], order='last_message_date desc', limit=1)
            for channel in channels:
                if self.template_id:
                    values = self.template_id.get_variable_values(channel)
                    channel.action_send_template(self.template_id.name, self.template_id.language, values)
                elif self.message_body:
                    channel.action_send_text(self.message_body)

    @api.model
    def _run_for_leads(self, leads, trigger):
        for rule in self.search([('active', '=', True), ('trigger', '=', trigger)]):
            for lead in leads.filtered(lambda item: rule._matches(item, trigger)):
                try:
                    rule._run_action(lead)
                except Exception:
                    # Una regla no debe bloquear el guardado del CRM por un
                    # canal desconectado o por una plantilla mal configurada.
                    lead.message_post(body=_('La regla %s no pudo ejecutarse.') % rule.name)

    @api.model
    def _cron_process_rules(self):
        leads = self.env['crm.lead'].search([
            ('active', '=', True), ('probability', '<', 100),
        ])
        today = fields.Date.context_today(self)
        for rule in self.search([
            ('active', '=', True), ('trigger', 'in', ('no_activity', 'specific_date')),
            '|', ('last_run_date', '!=', today), ('last_run_date', '=', False),
        ]):
            for lead in leads.filtered(lambda item: rule._matches(item, rule.trigger)):
                try:
                    rule._run_action(lead)
                except Exception:
                    lead.message_post(body=_('La regla %s no pudo ejecutarse.') % rule.name)
            rule.last_run_date = today

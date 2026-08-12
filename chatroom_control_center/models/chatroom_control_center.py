from odoo import api, fields, models, _


class ChatroomControlCenter(models.TransientModel):
    _name = 'chatroom.control.center'
    _description = 'Centro de control de Chatroom'

    whatsapp_status = fields.Selection(
        selection=[
            ('ready', 'Listo'),
            ('attention', 'Requiere configuración'),
            ('not_installed', 'No instalado'),
        ], compute='_compute_status', string='WhatsApp', readonly=True,
    )
    payment_status = fields.Selection(
        selection=[
            ('ready', 'Disponible'),
            ('not_installed', 'Módulo opcional'),
        ], compute='_compute_status', string='Payment Links', readonly=True,
    )
    payphone_status = fields.Selection(
        selection=[
            ('ready', 'Configurado'),
            ('attention', 'Requiere configuración'),
            ('not_installed', 'No instalado'),
        ], compute='_compute_status', string='PayPhone', readonly=True,
    )
    calendar_status = fields.Selection(
        selection=[
            ('ready', 'Disponible'),
            ('not_installed', 'Módulo opcional'),
        ], compute='_compute_status', string='Calendario', readonly=True,
    )
    ui_status = fields.Selection(
        selection=[
            ('ready', 'Activo'),
            ('not_installed', 'No instalado'),
        ], compute='_compute_status', string='Chatroom UI', readonly=True,
    )
    status_summary = fields.Char(
        compute='_compute_status', string='Resumen', readonly=True,
    )
    open_conversation_count = fields.Integer(
        compute='_compute_status', string='Conversaciones activas', readonly=True)
    sla_attention_count = fields.Integer(
        compute='_compute_status', string='Conversaciones con SLA', readonly=True)
    pending_payment_count = fields.Integer(
        compute='_compute_status', string='Pagos pendientes', readonly=True)
    rfm_rule_count = fields.Integer(
        compute='_compute_status', string='Reglas RFM activas', readonly=True)
    rfm_reactivation_count = fields.Integer(
        compute='_compute_status', string='Clientes para reactivar', readonly=True)

    @api.model
    def action_open_center(self):
        record = self.create({})
        return {
            'type': 'ir.actions.act_window',
            'name': _('Centro de control'),
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': record.id,
            'target': 'current',
        }

    def _module_installed(self, module_name):
        return bool(self.env['ir.module.module'].sudo().search_count([
            ('name', '=', module_name), ('state', '=', 'installed'),
        ]))

    @api.depends()
    def _compute_status(self):
        config = self.env['ir.config_parameter'].sudo()
        for record in self:
            whatsapp_installed = self._module_installed('chatroom_whatsapp')
            whatsapp_ready = all(config.get_param(key) for key in (
                'chatroom_whatsapp.phone_number_id',
                'chatroom_whatsapp.access_token',
                'chatroom_whatsapp.business_account_id',
            ))
            record.whatsapp_status = (
                'ready' if whatsapp_ready else 'attention'
            ) if whatsapp_installed else 'not_installed'

            record.payment_status = (
                'ready' if self._module_installed('chatroom_payment')
                else 'not_installed'
            )

            if not self._module_installed('payment_payphone') or 'payment.provider' not in self.env:
                record.payphone_status = 'not_installed'
            else:
                providers = self.env['payment.provider'].sudo().search([
                    ('code', '=', 'payphone'),
                    ('state', 'in', ('enabled', 'test')),
                ], limit=1)
                record.payphone_status = (
                    'ready' if providers and providers.payphone_token and providers.payphone_store_id
                    else 'attention'
                )

            record.calendar_status = (
                'ready' if self._module_installed('chatroom_calendar')
                else 'not_installed'
            )
            record.ui_status = (
                'ready' if self._module_installed('chatroom_ui')
                else 'not_installed'
            )

            record.open_conversation_count = 0
            record.sla_attention_count = 0
            if 'chatroom.channel' in self.env:
                channels = self.env['chatroom.channel'].sudo().search_read(
                    [('state', 'in', ('open', 'pending'))],
                    ['first_response_sla_state'])
                record.open_conversation_count = len(channels)
                record.sla_attention_count = sum(
                    row.get('first_response_sla_state') in ('yellow', 'red')
                    for row in channels
                )

            record.pending_payment_count = 0
            if 'payment.transaction' in self.env:
                record.pending_payment_count = self.env['payment.transaction'].sudo().search_count([
                    ('state', '=', 'pending'),
                ])

            record.rfm_rule_count = 0
            record.rfm_reactivation_count = 0
            if 'rfm.reactivation.rule' in self.env:
                rules = self.env['rfm.reactivation.rule'].sudo().search([
                    ('active', '=', True),
                ])
                record.rfm_rule_count = len(rules)
                categories = rules.mapped('category_code')
                if categories and 'res.partner' in self.env:
                    record.rfm_reactivation_count = self.env['res.partner'].sudo().search_count([
                        ('rfm_category', 'in', categories),
                    ])

            attention_count = sum(
                status == 'attention' for status in (
                    record.whatsapp_status, record.payphone_status,
                )
            )
            record.status_summary = (
                _('Hay %s integración(es) que requieren configuración.') % attention_count
                if attention_count else _('Las integraciones principales están listas.')
            )

    def action_refresh(self):
        return self.action_open_center()

    def _notification(self, message):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': _('Chatroom'), 'message': message, 'type': 'warning'},
        }

    def action_open_chatroom(self):
        return self.env.ref('chatroom_whatsapp.action_chatroom_app').read()[0]

    def action_open_settings(self):
        return self.env.ref('base_setup.action_general_configuration').read()[0]

    def action_open_payments(self):
        if 'payment.provider' not in self.env:
            return self._notification(_('Instala el módulo de pagos para administrar proveedores.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Proveedores de pago'),
            'res_model': 'payment.provider',
            'view_mode': 'list,form',
            'domain': [('code', '=', 'payphone')],
        }

    def action_open_calendar(self):
        if 'calendar.event' not in self.env:
            return self._notification(_('Instala Calendario para administrar reuniones.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Reuniones'),
            'res_model': 'calendar.event',
            'view_mode': 'calendar,list,form',
        }

    def action_open_rfm_dashboard(self):
        if 'crm.rfm.category' not in self.env:
            return self._notification(_('Instala Inteligencia Comercial para abrir el dashboard RFM.'))
        return self.env.ref(
            'crm_customer_intelligence.action_customer_intelligence_dashboard').read()[0]

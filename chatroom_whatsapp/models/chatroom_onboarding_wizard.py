# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError

ONBOARDING_STEPS = ['intro', 'credentials', 'webhook', 'test']


class ChatroomWhatsappOnboardingWizard(models.TransientModel):
    """Asistente paso a paso para configurar la Cloud API de WhatsApp:
    en vez de dejar al usuario solo frente a 6 campos sueltos en Ajustes
    (y sin saber en qué orden llenarlos ni cómo confirmar que quedaron
    bien), lo guía credencial por credencial y termina probando la
    conexión real contra Meta antes de cerrar."""
    _name = 'chatroom.whatsapp.onboarding.wizard'
    _description = "Asistente de configuración de WhatsApp Business"

    state = fields.Selection(
        [('intro', "Bienvenida"),
         ('credentials', "Credenciales"),
         ('webhook', "Webhook"),
         ('test', "Probar conexión")],
        default='intro', required=True)

    access_token = fields.Char(string="Token de acceso permanente")
    phone_number_id = fields.Char(string="Phone Number ID")
    business_account_id = fields.Char(string="WhatsApp Business Account ID")
    graph_api_version = fields.Char(string="Versión de la Graph API", default='v20.0')

    webhook_verify_token = fields.Char(string="Webhook Verify Token")
    app_secret = fields.Char(string="App Secret")
    webhook_url = fields.Char(string="URL del Webhook", compute='_compute_webhook_url')

    connection_result = fields.Text(string="Resultado de la prueba", readonly=True)
    connection_ok = fields.Boolean(readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        icp = self.env['ir.config_parameter'].sudo()
        res.update({
            'access_token': icp.get_param('chatroom_whatsapp.access_token', ''),
            'phone_number_id': icp.get_param('chatroom_whatsapp.phone_number_id', ''),
            'business_account_id': icp.get_param('chatroom_whatsapp.business_account_id', ''),
            'graph_api_version': icp.get_param('chatroom_whatsapp.graph_api_version', 'v20.0'),
            'webhook_verify_token': icp.get_param('chatroom_whatsapp.webhook_verify_token', ''),
            'app_secret': icp.get_param('chatroom_whatsapp.app_secret', ''),
        })
        return res

    def _compute_webhook_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for rec in self:
            rec.webhook_url = f"{base_url}/chatroom_whatsapp/webhook"

    def _reopen(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_next(self):
        self.ensure_one()
        if self.state == 'credentials':
            self._save_credentials()
        elif self.state == 'webhook':
            self._save_webhook_config()
        idx = ONBOARDING_STEPS.index(self.state)
        self.state = ONBOARDING_STEPS[min(idx + 1, len(ONBOARDING_STEPS) - 1)]
        return self._reopen()

    def action_back(self):
        self.ensure_one()
        idx = ONBOARDING_STEPS.index(self.state)
        self.state = ONBOARDING_STEPS[max(idx - 1, 0)]
        return self._reopen()

    def _save_credentials(self):
        self.ensure_one()
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('chatroom_whatsapp.access_token', self.access_token or '')
        icp.set_param('chatroom_whatsapp.phone_number_id', self.phone_number_id or '')
        icp.set_param('chatroom_whatsapp.business_account_id', self.business_account_id or '')
        icp.set_param('chatroom_whatsapp.graph_api_version', self.graph_api_version or 'v20.0')

    def _save_webhook_config(self):
        self.ensure_one()
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('chatroom_whatsapp.webhook_verify_token', self.webhook_verify_token or '')
        icp.set_param('chatroom_whatsapp.app_secret', self.app_secret or '')

    def action_test_connection(self):
        """Reutiliza la misma prueba de conexión de Ajustes (lee las
        credenciales recién guardadas desde ir.config_parameter, no
        duplica la llamada a la Graph API)."""
        self.ensure_one()
        settings = self.env['res.config.settings'].create({})
        try:
            result = settings.action_test_whatsapp_connection()
            self.connection_result = result['params']['message']
            self.connection_ok = True
        except UserError as exc:
            self.connection_result = str(exc)
            self.connection_ok = False
        return self._reopen()

    def action_finish(self):
        return {'type': 'ir.actions.act_window_close'}

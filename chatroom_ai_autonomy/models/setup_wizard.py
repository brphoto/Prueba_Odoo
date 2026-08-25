# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class ChatroomAiAutonomySetup(models.TransientModel):
    _name = 'chatroom.ai.autonomy.setup'
    _description = 'Configuración guiada de IA de Chatroom'

    company_id = fields.Many2one(
        'res.company', string='Empresa', default=lambda self: self.env.company,
        required=True)
    profile_name = fields.Char(string='Nombre del perfil', default='Perfil comercial principal', required=True)
    include_company = fields.Boolean(string='Datos de empresa', default=True)
    include_products = fields.Boolean(string='Productos y precios', default=True)
    include_stock = fields.Boolean(string='Stock disponible', default=True)
    include_customer = fields.Boolean(string='Datos del cliente', default=True)
    include_rfm = fields.Boolean(string='RFM y segmentación', default=True)
    policy_name = fields.Char(string='Nombre de la política', default='Operación segura', required=True)
    mode = fields.Selection([
        ('assist', 'Solo sugerencias'), ('approval', 'Con aprobación humana'),
        ('autonomous', 'Autonomía controlada'),
    ], string='Modo de operación', default='approval', required=True)
    allow_reply = fields.Boolean(string='Permitir respuestas automáticas', default=True)
    allow_quotation = fields.Boolean(string='Permitir preparar cotizaciones', default=True)
    allow_order = fields.Boolean(string='Permitir confirmar pedidos', default=False)
    allow_payment = fields.Boolean(string='Permitir links de pago', default=False)
    allow_delivery = fields.Boolean(string='Notificar entregas', default=True)
    max_order_amount = fields.Monetary(
        string='Monto máximo por pedido', currency_field='currency_id', default=0.0,
        help='Usa cero para no establecer un límite monetario.')
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', readonly=True)
    configuration_message = fields.Char(
        string='Revisión de configuración', compute='_compute_configuration_message')

    @api.depends(
        'mode', 'allow_reply', 'allow_quotation', 'allow_order',
        'allow_payment', 'allow_delivery', 'max_order_amount')
    def _compute_configuration_message(self):
        for wizard in self:
            if wizard.allow_order and wizard.max_order_amount <= 0:
                wizard.configuration_message = _(
                    'Pedidos habilitados sin límite monetario explícito. Define un monto máximo si quieres controlarlo.')
            elif wizard.mode == 'assist':
                wizard.configuration_message = _(
                    'Modo sugerencias: la IA preparará propuestas, pero no enviará ni confirmará por sí sola.')
            elif wizard.mode == 'approval':
                wizard.configuration_message = _(
                    'Modo supervisado: las acciones sensibles pedirán aprobación humana.')
            elif wizard.mode == 'autonomous' and (wizard.allow_order or wizard.allow_payment):
                wizard.configuration_message = _(
                    'Autonomía controlada: pedidos y pagos seguirán sujetos a sus límites y herramientas autorizadas.')
            else:
                wizard.configuration_message = _(
                    'Configuración válida: revisa el resumen y pulsa Aplicar y sincronizar.')

    def action_apply(self):
        self.ensure_one()
        Profile = self.env['chatroom.ai.knowledge.profile'].sudo()
        Policy = self.env['chatroom.ai.autonomy.policy'].sudo()
        profile = Profile.search([('company_id', '=', self.company_id.id)], order='sequence, id', limit=1)
        values = {
            'name': self.profile_name,
            'company_id': self.company_id.id,
            'include_company': self.include_company,
            'include_products': self.include_products,
            'include_stock': self.include_stock,
            'include_customer': self.include_customer,
            'include_rfm': self.include_rfm,
            'state': 'draft',
        }
        profile = profile or Profile.create(values)
        profile.write(values)
        profile.action_set_default()
        policy = Policy.search([('company_id', '=', self.company_id.id)], order='sequence, id', limit=1)
        policy = policy or Policy.create({
            'name': self.policy_name, 'company_id': self.company_id.id,
        })
        policy.write({
            'name': self.policy_name, 'mode': self.mode,
            'allow_reply': self.allow_reply, 'allow_quotation': self.allow_quotation,
            'allow_order': self.allow_order, 'allow_payment': self.allow_payment,
            'allow_delivery': self.allow_delivery,
            'max_order_amount': self.max_order_amount,
        })
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'title': _('Configuración aplicada'),
                'message': _('Perfil sincronizado y política segura preparada. Las acciones de pedido y pago permanecen desactivadas si no las autorizaste.'),
                'type': 'success', 'sticky': False,
            },
        }

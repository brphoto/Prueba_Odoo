# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ChatroomKnowledgeProfile(models.Model):
    _name = 'chatroom.ai.knowledge.profile'
    _description = 'Perfil de conocimiento operativo de Chatroom'
    _order = 'sequence, name'

    name = fields.Char(string='Nombre del perfil', required=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one(
        'res.company', string='Empresa', default=lambda self: self.env.company,
        required=True, index=True)
    include_company = fields.Boolean(string='Datos de la empresa', default=True)
    include_products = fields.Boolean(string='Productos y precios', default=True)
    include_stock = fields.Boolean(string='Disponibilidad de inventario', default=True)
    include_customer = fields.Boolean(string='Ficha del cliente', default=True)
    include_rfm = fields.Boolean(string='RFM y segmentación', default=True)
    product_limit = fields.Integer(string='Máximo de productos', default=8)
    context_max_chars = fields.Integer(string='Máximo de contexto', default=7000)
    last_sync_at = fields.Datetime(string='Última sincronización', readonly=True)
    state = fields.Selection([
        ('draft', 'Sin sincronizar'), ('ready', 'Listo'), ('error', 'Error'),
    ], string='Estado', default='draft', readonly=True)
    last_result = fields.Char(string='Resultado', readonly=True)
    product_count = fields.Integer(string='Productos disponibles', readonly=True)
    partner_count = fields.Integer(string='Clientes disponibles', readonly=True)
    source_summary = fields.Text(string='Fuentes activas', readonly=True)
    sync_guidance = fields.Char(
        string='Orientación', compute='_compute_sync_guidance')

    @api.depends('state', 'last_sync_at', 'source_summary', 'product_count', 'partner_count')
    def _compute_sync_guidance(self):
        for record in self:
            if record.state == 'ready':
                record.sync_guidance = _(
                    'Conocimiento local listo: %s productos y %s clientes disponibles para consultar.') % (
                        record.product_count, record.partner_count)
            elif record.state == 'error':
                record.sync_guidance = _(
                    'La última sincronización tuvo un problema. Revisa el resultado y vuelve a intentarlo.')
            else:
                record.sync_guidance = _(
                    'Aún no sincronizado. Pulsa «Sincronizar ahora» para preparar las fuentes locales.')

    @api.constrains('product_limit', 'context_max_chars')
    def _check_limits(self):
        for record in self:
            if not 1 <= record.product_limit <= 100:
                raise ValidationError(_('El máximo de productos debe estar entre 1 y 100.'))
            if not 1000 <= record.context_max_chars <= 20000:
                raise ValidationError(_('El contexto debe estar entre 1.000 y 20.000 caracteres.'))

    def action_sync(self):
        ICP = self.env['ir.config_parameter'].sudo()
        for record in self:
            try:
                if record.include_products:
                    product_count = self.env['product.product'].sudo().search_count([
                        ('sale_ok', '=', True), ('active', '=', True),
                    ])
                else:
                    product_count = 0
                partner_count = self.env['res.partner'].sudo().search_count([
                    ('active', '=', True),
                ]) if record.include_customer else 0
                ICP.set_param('chatroom_ai.knowledge_product_limit', record.product_limit)
                ICP.set_param('chatroom_ai.knowledge_context_max_chars', record.context_max_chars)
                sources = []
                if record.include_company:
                    sources.append(_('empresa'))
                if record.include_products:
                    sources.append(_('productos y precios'))
                if record.include_stock:
                    sources.append(_('inventario vivo'))
                if record.include_customer:
                    sources.append(_('clientes'))
                if record.include_rfm:
                    sources.append(_('RFM'))
                record.write({
                    'last_sync_at': fields.Datetime.now(),
                    'state': 'ready',
                    'last_result': _('Perfil sincronizado localmente; no consume tokens.'),
                    'product_count': product_count,
                    'partner_count': partner_count,
                    'source_summary': ', '.join(sources),
                })
            except Exception as error:  # noqa: BLE001
                record.write({'state': 'error', 'last_result': str(error)})
        return True

    def action_set_default(self):
        self.ensure_one()
        self.env['ir.config_parameter'].sudo().set_param(
            'chatroom_ai.knowledge_profile_id', self.id)
        self.action_sync()
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'title': _('Perfil activo'),
                'message': _('El perfil «%s» quedó activo para las consultas de IA.') % self.name,
                'type': 'success', 'sticky': False,
            },
        }

# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, fields, models


class ChatroomOperationsDemo(models.TransientModel):
    _name = 'chatroom.operations.demo'
    _description = 'Generador de escenarios DEMO QA'

    name = fields.Char(string='Lote de demostración', default='DEMO QA')
    scenario_count = fields.Integer(string='Escenarios estándar', readonly=True, default=6)
    result = fields.Text(string='Resultado', readonly=True)

    def action_generate(self):
        self.ensure_one()
        Partner = self.env['res.partner'].sudo()
        Channel = self.env['chatroom.channel'].sudo()
        Product = self.env['product.template'].sudo().search([('name', '=', 'DEMO QA - Producto de prueba')], limit=1)
        if not Product:
            Product = self.env['product.template'].sudo().create({'name': 'DEMO QA - Producto de prueba', 'list_price': 35.0, 'sale_ok': True})
        scenarios = [('Carrito abandonado', 'collecting'), ('Esperando confirmación', 'awaiting_confirmation'), ('Pedido confirmado', 'confirmed'), ('Pago recibido', 'post_sale'), ('Entrega lista', 'post_sale'), ('Escalado a humano', 'escalated')]
        ids = []
        for key, status in scenarios:
            partner = Partner.search([('name', '=', 'DEMO QA - ' + key)], limit=1) or Partner.create({'name': 'DEMO QA - ' + key, 'phone': '+593999700000'})
            external = 'demo-qa-' + key.lower().replace(' ', '-')
            channel = Channel.search([('external_id', '=', external), ('channel_type', '=', 'whatsapp')], limit=1)
            channel = channel or Channel.create({'channel_type': 'whatsapp', 'external_id': external, 'partner_id': partner.id})
            channel.write({'partner_id': partner.id, 'state': 'open', 'ai_sales_status': status})
            if key == 'Entrega lista' and 'ai_sales_delivery_status' in channel._fields:
                channel.ai_sales_delivery_status = 'ready'
            if key == 'Carrito abandonado' and 'chatroom.cart.line' in self.env:
                cart = self.env['chatroom.cart.line'].sudo().search([('channel_id', '=', channel.id)], limit=1)
                cart = cart or self.env['chatroom.cart.line'].sudo().create({'channel_id': channel.id, 'product_id': Product.product_variant_id.id, 'product_name': Product.product_variant_id.display_name, 'quantity': 1, 'price_unit': Product.list_price})
                self.env.cr.execute('UPDATE chatroom_cart_line SET create_date = %s WHERE id = %s', (fields.Datetime.now() - timedelta(days=2), cart.id))
            if key == 'Pago recibido' and 'chatroom.payment.link' in self.env:
                payment = self.env['chatroom.payment.link'].sudo().search([('channel_id', '=', channel.id)], limit=1)
                if not payment:
                    self.env['chatroom.payment.link'].sudo().create({
                        'name': 'DEMO QA - Pago recibido',
                        'channel_id': channel.id,
                        'link': 'https://example.test/demo-qa-pago',
                        'state': 'paid',
                    })
            if 'chatroom.ai.sales.event' in self.env and 'ai_sales_status' in channel._fields:
                event = 'escalated' if key == 'Escalado a humano' else 'payment_received' if key == 'Pago recibido' else 'order_confirmed' if key == 'Pedido confirmado' else False
                if event and not self.env['chatroom.ai.sales.event'].sudo().search_count([('channel_id', '=', channel.id), ('event', '=', event)]):
                    channel._sales_log(event, _('Escenario DEMO QA generado de forma segura.'))
            if key == 'Escalado a humano':
                channel.ai_sales_last_error = _('DEMO QA: revisión humana requerida.')
            ids.append('%s (%s)' % (channel.display_name, channel.id))
        Playbook = self.env['chatroom.operations.playbook'].sudo()
        for name, trigger in (
            ('DEMO QA - Aviso de carrito abandonado', 'cart_abandoned'),
            ('DEMO QA - Aviso de pago fallido', 'payment_failed'),
            ('DEMO QA - Aviso de entrega preparada', 'delivery_ready'),
        ):
            playbook = Playbook.with_context(active_test=False).search([('name', '=', name)], limit=1)
            if not playbook:
                playbook = Playbook.create({
                    'name': name,
                    'trigger': trigger,
                    'execution_mode': 'notify',
                    'approval_required': True,
                    'active': False,
                })
            else:
                playbook.write({'active': False})
        self.result = _('Escenarios disponibles:\n%s') % '\n'.join(ids)
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {'title': _('Demos QA'), 'message': _('Se generaron o actualizaron 6 escenarios DEMO QA.'), 'type': 'success'}}

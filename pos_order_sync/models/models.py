# -*- coding: utf-8 -*-
#################################################################################
#
#   Copyright (c) 2016-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#   See LICENSE file for full copyright and licensing details.
#   License URL : <https://store.webkul.com/license.html/>
#
#################################################################################
from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.translate import _
import logging
_logger = logging.getLogger(__name__)


class PosConfig(models.Model):
    _inherit = 'pos.config'

    quotation_print_type = fields.Selection([('pdf', 'Browser based (Pdf Report)'), (
        'posbox', 'POSBOX (Reporte XML)')], default='pdf', required=True, string="Tipo de impresión del pedido")
    enable_transfer_tracking = fields.Boolean(
        string="Registrar transferencias entre cajas",
        default=True,
        help="Registra el cajero que recibe un pedido transferido y lo muestra en los reportes de sesión.",
    )

    def _compute_all_active_session(self):
        for obj in self:
            all_session_ids = self.env['pos.session'].search(
                [('state', '=', 'opened')]).ids
            obj.all_active_session_ids = all_session_ids

    @api.constrains('quotation_print_type', 'iface_print_via_proxy')
    def check_hardware_connection(self):
        for obj in self:
            if (obj.quotation_print_type == 'posbox'):
                if(obj.iface_print_via_proxy == False):
                    raise UserError(
                        "No se puede imprimir el comprobante XML. Revisa la impresora en Hardware Proxy / PosBox.")


    @api.model
    def get_floors(self, kwargs):
        other_config = kwargs.get('other_config') or []
        if other_config:
            pos_config_info = self.env['pos.config'].browse(
                other_config)
            restaurant_installed = False
            for config in pos_config_info:
                if(config.module_pos_restaurant):
                    restaurant_installed = True
            if(restaurant_installed):
                floors = self.env['restaurant.floor'].search(
                    [('pos_config_ids', 'in', other_config)])
                data = []
                for floor in floors:
                    table_ids = []
                    for table_id in floor.table_ids:
                        table_ids.append(table_id.id)
                    data.append({'id': floor.id,
                                 'name': floor.name,
                                 'background_color': floor.background_color,
                                 'table_ids': table_ids,
                                 'sequence': floor.sequence,
                                 'pos_config_ids': floor.pos_config_ids.ids})
                return data
            else:
                return False

    @api.model
    def get_tables(self, kwargs):
        other_config = kwargs.get('other_config') or []
        if other_config:
            pos_config_info = self.env['pos.config'].browse(
                other_config)
            restaurant_installed = False
            for config in pos_config_info:
                if(config.module_pos_restaurant):
                    restaurant_installed = True

            if(restaurant_installed and kwargs.get('other_config')):
                floors = self.env['restaurant.floor'].search(
                    [('pos_config_ids', 'in', other_config)])
                data = []
                for floor in floors:
                    table_ids = []
                    for table_id in floor.table_ids:
                        table_ids.append(table_id.id)
                        data.append({"color": table_id.color,
                                     "floor_id": [floor.id, floor.name],
                                     "height": table_id.height,
                                     "id": table_id.id,
                                     "name": table_id.table_number,
                                     "position_h": table_id.position_h,
                                     "position_v": table_id.position_v,
                                     "seats": table_id.seats,
                                     "shape": table_id.shape,
                                     "width": table_id.width, })
                return data
            else:
                return False

    @api.model
    def load_products_for_pos(self, kwargs):
        """Load quoted products using the native Odoo 19 POS data format."""
        product_ids = [int(product_id) for product_id in (kwargs.get('product_ids') or []) if product_id]
        config = self.env['pos.config'].browse(int(kwargs.get('config_id'))).exists()
        if not product_ids or not config:
            return {}

        products = self.env['product.product'].browse(product_ids).exists()
        templates = products.mapped('product_tmpl_id')
        return {
            'product.template': self.env['product.template']._load_pos_data_read(templates, config),
            'product.product': self.env['product.product']._load_pos_data_read(products, config),
        }


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pos_quotation_print_type = fields.Selection(
        related='pos_config_id.quotation_print_type', readonly=False)
    pos_enable_transfer_tracking = fields.Boolean(
        related='pos_config_id.enable_transfer_tracking', readonly=False)


class PosSession(models.Model):
    _inherit = 'pos.session'

    transfer_sent_count = fields.Integer(compute='_compute_transfer_counts')
    transfer_received_count = fields.Integer(compute='_compute_transfer_counts')

    def _compute_transfer_counts(self):
        Quote = self.env['pos.quote']
        for session in self:
            session.transfer_sent_count = Quote.search_count([
                ('session_id', '=', session.id),
            ])
            session.transfer_received_count = Quote.search_count([
                ('to_session_id', '=', session.id),
            ])

    def _open_transfer_quotes(self, domain, title):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': title,
            'res_model': 'pos.quote',
            'view_mode': 'list,form',
            'domain': domain,
            'context': {'create': False},
        }

    def action_view_transfer_sent_quotes(self):
        self.ensure_one()
        return self._open_transfer_quotes(
            [('session_id', '=', self.id)],
            'Pedidos enviados desde esta caja',
        )

    def action_view_transfer_received_quotes(self):
        self.ensure_one()
        return self._open_transfer_quotes(
            [('to_session_id', '=', self.id)],
            'Pedidos recibidos en esta caja',
        )


class PosOrder(models.Model):
    _inherit = "pos.order"

    quote_id = fields.Many2one("pos.quote", string="Related Quote", copy=False, index=True)
    seller_name = fields.Char("Vendedor Origen", copy=False)
    cashier_name = fields.Char("Nombre Cajero", copy=False)
    quote_name= fields.Char("Quote Name", copy=False)

    @api.model
    def _load_pos_data_fields(self, config):
        """Expose synchronization fields to Odoo 19's POS data loader."""
        result = super()._load_pos_data_fields(config)
        # In Odoo 19 an empty result means: load all non-manual fields.
        # Returning only the addon fields would hide standard POS fields
        # such as uuid, lines, session_id and payment_ids.
        if not result:
            return result

        # Keep synchronization fields when another module uses a restricted
        # POS field list.  ``lines`` is required by the price computation.
        for field_name in ['lines', 'quote_id', 'seller_name', 'cashier_name', 'quote_name']:
            if field_name not in result:
                result.append(field_name)
        return result

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            if record.quote_id:
                record.quote_id.sudo().write({
                    'state': 'done',
                    'received_order_id': record.id,
                })
        return records

class PosQuotes(models.Model):
    _name = 'pos.quote'
    _description = "Pos Quotes"
    _rec_name = 'quote_id'

    quote_id = fields.Char('Número de pedido', readonly=True)
    table_json = fields.Text("Datos de mesa")
    pos_res_info = fields.Text("Información del restaurante")
    name = fields.Char("Nombre")
    user_id = fields.Many2one('res.users', 'Cajero origen')
    date_order = fields.Datetime('Fecha del pedido', readonly=True, index=True)
    lines = fields.One2many('pos.quote.line', 'quote_id',
                            'Quote Lines', readonly=True)
    pricelist_id = fields.Many2one(
        'product.pricelist', 'Pricelist', readonly=True)
    partner_id = fields.Many2one('res.partner', 'Customer')
    session_id = fields.Many2one(
        'pos.session', 'From POS Session', index=1, readonly=True)
    note = fields.Text('Internal Notes')
    to_session_id = fields.Many2one(
        'pos.session', 'To POS Session', index=1, readonly=True)
    amount_total = fields.Float(
        string='Total', digits=0,  readonly=True)
    amount_tax = fields.Float(
        string='Taxes', digits=0, readonly=True)
    state = fields.Selection([
        ("draft", "Pendiente"),
        ("done", "Completado"),
        ("cancel", "Cancelado")],
        default='draft')
    fiscal_position_id = fields.Many2one(
        'account.fiscal.position', 'Fiscal Position', readonly=True)
    quote_sent = fields.Boolean('Quote sent')
    trackingNumber = fields.Char("Tracking Number")
    seller_name= fields.Char('Vendedor Origen')
    received_user_id = fields.Many2one(
        'res.users', string='Cajero Receptor', readonly=True, copy=False)
    received_cashier_name = fields.Char(
        string='Nombre Cajero Receptor', readonly=True, copy=False)
    received_at = fields.Datetime(
        string='Fecha de Recepción', readonly=True, copy=False)
    received_order_id = fields.Many2one(
        'pos.order', string='Pedido POS Generado', readonly=True, copy=False)

    @api.model
    def search_quote(self, args):
        if args.get('quotation_id'):
            result = self.search(
                [('quote_id', '=', args.get('quotation_id'))]).id
            if result:
                return True

    def write(self, vals):
        for obj in self:
            if 'quote_id' in vals:
                found_ids = self.env['pos.quote'].search(
                    [('quote_id', '=', vals['quote_id'])]).ids
                if len(found_ids) > 0:
                    raise UserError(
                        "Usa otro número de pedido.\nEste número ya fue utilizado en otro pedido.")
        return super(PosQuotes, self).write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('quote_id') == '' or not vals.get('quote_id'):
                vals['quote_id'] = self.env['ir.sequence'].next_by_code(
                    'pos.quote')

            for field in ['amount_total', 'amount_tax']:
                if field in vals and isinstance(vals[field], str):
                    vals[field] = float(vals[field].replace(',', ''))
            if vals.get('seller_name'):
                vals['seller_name'] = vals.get('seller_name')

        result = super(PosQuotes, self).create(vals_list)
        return result

    @api.model
    def print_quote(self):
        report_ids = self.env['ir.actions.report'].search([(
            'model', '=', 'pos.quote'), ('report_name', '=', 'pos_order_sync.quote_order_report')]).ids
        return report_ids and report_ids[0] or False

    @api.model
    def mark_received(self, quote_id, user_id=False, cashier_name=False):
        quote = self.browse(int(quote_id)).exists()
        if not quote:
            return False
        if not quote.to_session_id or not quote.to_session_id.config_id.enable_transfer_tracking:
            return False
        receiver = self.env['res.users'].browse(int(user_id)).exists() if user_id else self.env['res.users']
        quote.sudo().write({
            'received_user_id': receiver.id if receiver else False,
            'received_cashier_name': cashier_name or (receiver.name if receiver else self.env.user.name),
            'received_at': fields.Datetime.now(),
        })
        return True

    @api.model
    def search_all_record(self, kwargs):
        results = {}
        record_list = []
        quote_ids = self.search([('quote_id', 'not in', kwargs['quote_ids']), ('state', '=', 'draft'),
                                 ('to_session_id', '=', kwargs['session_id'])]).ids

        quote_objs = self.browse(quote_ids)
        for quote_obj in quote_objs:
            result = {}
            result["status"] = True
            result["state"] = quote_obj.state
            result['quote_obj_id'] = quote_obj.id
            result['quote_id'] = quote_obj.quote_id
            result['pricelist_id'] = quote_obj.pricelist_id.id
            result['note'] = quote_obj.note
            result['amount_total'] = quote_obj.amount_total
            result['amount_tax'] = quote_obj.amount_tax
            result['partner_id'] = [
                quote_obj.partner_id.id, quote_obj.partner_id.name or '-']
            result['to_session_id'] = quote_obj.to_session_id.id
            result['from_session_id'] = quote_obj.session_id.config_id.display_name or '-'
            result['message'] = 'El número del pedido no pertenece a esta sesión de Punto de Venta.'
            result['seller_name'] = quote_obj.seller_name or '-'
            result['received_user_id'] = [
                quote_obj.received_user_id.id,
                quote_obj.received_user_id.name or '-',
            ] if quote_obj.received_user_id else False
            result['received_cashier_name'] = quote_obj.received_cashier_name or '-'
            if(quote_obj.table_json):
                result['table_json'] = quote_obj.table_json
            result['line'] = []
            for line in quote_obj.lines:
                orderline = {}
                orderline['product_id'] = line.product_id.id
                orderline['price_unit'] = line.price_unit
                orderline['qty'] = line.qty
                orderline['discount'] = line.discount
                orderline['so_reference'] = line.so_reference
                orderline['sale_order_origin_id'] = [
                    line.sale_order_origin_id.id,
                    line.sale_order_origin_id.name or '',
                ]
                result['line'].append(orderline)
            record_list.append(result)
        results['quote_list'] = record_list
        return results

    @api.model
    def load_quote_history(self, kwargs):
        results = {}
        quote_list = []
        quote_objs = self.search([('session_id', '=', int(kwargs.get('session_id')))])
        for quote_obj in quote_objs:
            result = {}
            result['quote_id'] = quote_obj.quote_id
            if quote_obj.partner_id and quote_obj.partner_id.name:
                result['partner_id'] = quote_obj.partner_id.name
            else:
                result['partner_id'] = '-'
            result['amount_total'] = quote_obj.amount_total
            result['to_session_id'] = (
                quote_obj.to_session_id.config_id.display_name
                if quote_obj.to_session_id else '-'
            )
            result["state"] = {
                'draft': 'Pendiente',
                'done': 'Completado',
                'cancel': 'Cancelado',
            }.get(quote_obj.state, '-')
            result['seller_name'] = quote_obj.seller_name or '-'
            quote_list.append(result)
        results['quote_list'] = quote_list
        return results

    def click_cancel(self):
        for obj in self:
            obj.state = 'cancel'

    @api.depends('quote_id')
    def name_get(self):
        '''Overridden name_get() method for returning the registered number as name'''
        res = []
        for record in self:
            name = str(record.quote_id)
            res.append((record.id, name))
        return res

class PosQuoteLine(models.Model):
    _name = 'pos.quote.line'
    _description = "Pos Quote Line"

    quote_id = fields.Many2one("pos.quote")
    name = fields.Char("Line", default="Quote Line")
    product_id = fields.Many2one('product.product', 'Product', domain=[(
        'sale_ok', '=', True), ('available_in_pos', '=', True)], required=True, change_default=True)
    price_unit = fields.Float(string='Unit Price', digits=0)
    qty = fields.Float('Quantity')
    price_subtotal = fields.Float(digits=0, string='Subtotal w/o Tax')
    price_subtotal_incl = fields.Float(digits=0, string='Subtotal')
    discount = fields.Float('Discount (%)', digits=0)
    tax_ids = fields.Many2many('account.tax', string='Taxes')
    # tax_ids_after_fiscal_position = fields.Many2many('account.tax', string='Taxes')
    so_reference = fields.Char("Referencia SO")
    sale_order_origin_id = fields.Many2one('sale.order', string="Linked Sale Order")
    notice = fields.Char('Discount Notice')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'quote_tax_ids' in vals:
                tax_ids_list = vals['quote_tax_ids']
                vals['tax_ids'] = [(6, 0, tax_ids_list)]
                del vals['quote_tax_ids']
        record = super(PosQuoteLine, self).create(vals_list)
        return record


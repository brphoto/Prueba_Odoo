from odoo import _, api, fields, models
from odoo.exceptions import UserError


class MarketingProductCatalogItem(models.Model):
    _name = 'marketing.product.catalog.item'
    _description = 'Elemento del catálogo comercial'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'active desc, name, id'

    product_tmpl_id = fields.Many2one(
        'product.template', string='Producto de Odoo', required=True,
        ondelete='cascade', index=True, tracking=True)
    name = fields.Char(
        string='Nombre comercial', related='product_tmpl_id.name', store=True,
        readonly=True)
    default_code = fields.Char(
        string='Referencia interna', related='product_tmpl_id.default_code',
        readonly=True)
    description_sale = fields.Text(
        string='Descripción para venta', related='product_tmpl_id.description_sale',
        readonly=True)
    product_type = fields.Selection(
        string='Tipo', related='product_tmpl_id.type', readonly=True)
    category_id = fields.Many2one(
        'product.category', string='Categoría', related='product_tmpl_id.categ_id',
        readonly=True)
    list_price = fields.Float(
        string='Precio de venta', related='product_tmpl_id.list_price',
        readonly=True)
    currency_id = fields.Many2one(
        'res.currency', string='Moneda', related='product_tmpl_id.currency_id',
        readonly=True)
    available_qty = fields.Float(
        string='Existencias disponibles', compute='_compute_available_qty', readonly=True)
    uom_id = fields.Many2one(
        'uom.uom', string='Unidad de medida', related='product_tmpl_id.uom_id',
        readonly=True)
    image_1920 = fields.Image(
        string='Imagen', related='product_tmpl_id.image_1920', readonly=True)
    active = fields.Boolean(default=True, tracking=True)
    include_in_catalog = fields.Boolean(
        string='Incluir en catálogo', default=True, tracking=True,
        help='Controla si el producto se presenta como oferta comercial disponible.')
    catalog_state = fields.Selection([
        ('draft', 'Borrador'), ('ready', 'Listo'), ('blocked', 'Bloqueado'),
    ], string='Estado comercial', default='draft', tracking=True)
    availability = fields.Selection([
        ('available', 'Disponible'), ('out_of_stock', 'Agotado'),
        ('service', 'Servicio'), ('inactive', 'Inactivo'),
    ], string='Disponibilidad', compute='_compute_availability', store=True)
    public_url = fields.Char(
        string='Enlace comercial',
        help='Enlace opcional a la ficha pública del producto o servicio.')
    last_sync_at = fields.Datetime(string='Última actualización', readonly=True)
    sync_message = fields.Char(string='Detalle de sincronización', readonly=True)
    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True,
        default=lambda self: self.env.company, index=True)

    _catalog_product_unique = models.Constraint(
        'unique(product_tmpl_id, company_id)',
        'Este producto ya está incluido en el catálogo de esta compañía.')

    @api.depends('product_tmpl_id')
    def _compute_available_qty(self):
        for record in self:
            variant = record.product_tmpl_id.product_variant_id
            record.available_qty = variant.qty_available if variant and 'qty_available' in variant._fields else 0.0

    @api.depends('active', 'include_in_catalog', 'available_qty', 'product_type')
    def _compute_availability(self):
        for record in self:
            if not record.active or not record.include_in_catalog:
                record.availability = 'inactive'
            elif record.product_type == 'service':
                record.availability = 'service'
            elif record.available_qty > 0:
                record.availability = 'available'
            else:
                record.availability = 'out_of_stock'

    @api.model
    def action_sync_from_products(self):
        """Create/update the commercial catalog from native Odoo products."""
        Product = self.env['product.template']
        company = self.env.company
        products = Product.search([
            ('active', '=', True), ('sale_ok', '=', True),
            '|', ('company_id', '=', False), ('company_id', '=', company.id),
        ], order='name')
        now = fields.Datetime.now()
        for product in products:
            item = self.search([
                ('product_tmpl_id', '=', product.id), ('company_id', '=', company.id),
            ], limit=1)
            values = {
                'product_tmpl_id': product.id,
                'company_id': company.id,
                'active': True,
                'catalog_state': 'ready',
                'last_sync_at': now,
                'sync_message': _('Información tomada del producto nativo de Odoo.'),
            }
            if item:
                item.write(values)
            else:
                self.create(dict(values, include_in_catalog=True))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Catálogo comercial'),
            'res_model': self._name,
            'view_mode': 'kanban,list,form',
            'domain': [('company_id', '=', company.id)],
        }

    def action_refresh_from_product(self):
        self.ensure_one()
        self.write({
            'last_sync_at': fields.Datetime.now(),
            'catalog_state': 'ready',
            'sync_message': _('Datos actualizados desde el producto nativo de Odoo.'),
        })
        return True

    def action_open_product(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Producto de Odoo'),
            'res_model': 'product.template',
            'res_id': self.product_tmpl_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_open_public_url(self):
        self.ensure_one()
        if not self.public_url:
            raise UserError(_('Este elemento no tiene un enlace comercial configurado.'))
        return {'type': 'ir.actions.act_url', 'url': self.public_url, 'target': 'new'}

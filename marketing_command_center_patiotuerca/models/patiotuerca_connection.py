import base64
import json
import logging
from datetime import timedelta

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class MarketingPatiotuercaConnection(models.Model):
    _name = 'marketing.patiotuerca.connection'
    _description = 'Conexión de catálogo Patiotuerca'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'active desc, name'

    name = fields.Char(string='Nombre de la conexión', required=True, tracking=True)
    endpoint_url = fields.Char(
        string='Endpoint del catálogo',
        help='URL del feed JSON o API entregada por Patiotuerca. El conector acepta data, items o una lista raíz.')
    api_token = fields.Char(string='Token de acceso', groups='marketing_command_center_patiotuerca.group_patiotuerca_manager')
    feed_file = fields.Binary(
        string='Archivo JSON del catálogo', attachment=True,
        help='Alternativa al endpoint para validar un export de Patiotuerca. Debe contener una lista o data, items, vehicles o listings.')
    feed_filename = fields.Char(string='Nombre del archivo')
    active = fields.Boolean(default=True, tracking=True)
    demo_mode = fields.Boolean(string='Modo demo', default=False)
    state = fields.Selection([
        ('draft', 'Sin probar'), ('connected', 'Conectada'),
        ('error', 'Con error'), ('demo', 'Datos demo'),
    ], string='Estado', default='draft', readonly=True, tracking=True)
    last_sync_at = fields.Datetime(string='Última sincronización', readonly=True)
    last_sync_summary = fields.Text(string='Resultado de la última sincronización', readonly=True)
    last_error = fields.Text(string='Detalle técnico', readonly=True)
    listing_ids = fields.One2many('marketing.vehicle.listing', 'connection_id', string='Vehículos')
    listing_count = fields.Integer(compute='_compute_counts', string='Vehículos')
    published_count = fields.Integer(compute='_compute_counts', string='Publicados')
    unpublished_count = fields.Integer(compute='_compute_counts', string='Despublicados')
    stale_count = fields.Integer(compute='_compute_counts', string='Sin actualizar')
    stale_after_hours = fields.Integer(
        string='Desactualizado después de (horas)', default=48, required=True,
        help='Detecta anuncios que dejaron de aparecer en el feed. No cambia el estado automáticamente.')
    mark_missing_unpublished = fields.Boolean(
        string='Marcar ausentes como despublicados',
        help='En feeds completos, marca como despublicados los anuncios publicados que ya no aparecen. Déjalo desactivado si el feed es parcial.')
    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True,
        default=lambda self: self.env.company, index=True)

    @api.depends('listing_ids', 'listing_ids.status', 'listing_ids.is_stale')
    def _compute_counts(self):
        for record in self:
            listings = record.listing_ids
            record.listing_count = len(listings)
            record.published_count = len(listings.filtered(lambda item: item.status == 'published'))
            record.unpublished_count = len(listings.filtered(lambda item: item.status != 'published'))
            record.stale_count = len(listings.filtered('is_stale'))

    @api.constrains('stale_after_hours')
    def _check_stale_after_hours(self):
        for record in self:
            if record.stale_after_hours < 1 or record.stale_after_hours > 8760:
                raise ValidationError(_('El tiempo de desactualización debe estar entre 1 y 8760 horas.'))

    def _headers(self):
        headers = {'Accept': 'application/json'}
        if self.api_token:
            headers['Authorization'] = 'Bearer %s' % self.api_token
        return headers

    def _request_rows(self):
        self.ensure_one()
        if self.feed_file:
            try:
                payload = json.loads(base64.b64decode(self.feed_file).decode('utf-8-sig'))
            except (ValueError, TypeError, UnicodeDecodeError) as exc:
                raise UserError(_('El archivo del catálogo no contiene JSON válido en UTF-8.')) from exc
        else:
            if not self.endpoint_url:
                raise UserError(_('Configura el endpoint o carga un archivo JSON del catálogo antes de sincronizar.'))
            response = requests.get(self.endpoint_url, headers=self._headers(), timeout=30)
            if response.status_code >= 400:
                raise UserError(_('El catálogo externo respondió HTTP %s.') % response.status_code)
            try:
                payload = response.json()
            except (ValueError, TypeError) as exc:
                raise UserError(_('El endpoint no devolvió JSON válido.')) from exc
        if isinstance(payload, list):
            return payload
        for key in ('data', 'items', 'vehicles', 'listings', 'results'):
            if isinstance(payload.get(key), list):
                return payload[key]
        raise UserError(_('El JSON no contiene una lista de vehículos. Usa data, items, vehicles o listings.'))

    @staticmethod
    def _value(row, *keys):
        for key in keys:
            if row.get(key) not in (None, ''):
                return row.get(key)
        return False

    @staticmethod
    def _number(value, default=0.0):
        """Convierte valores del proveedor sin romper toda la sincronización."""
        if value in (None, ''):
            return default
        try:
            if isinstance(value, str):
                value = value.replace(',', '').strip()
            return float(value)
        except (TypeError, ValueError):
            return default

    def _upsert_row(self, row, source='patiotuerca'):
        Listing = self.env['marketing.vehicle.listing']
        external_id = str(self._value(row, 'id', 'external_id', 'vehicle_id', 'listing_id') or '').strip()
        if not external_id:
            return False
        raw_status = str(self._value(row, 'status', 'state', 'publication_status', 'availability') or '').lower()
        status = 'published' if raw_status in ('published', 'publicado', 'active', 'online', 'activo') else (
            'sold' if raw_status in ('sold', 'vendido') else (
                'reserved' if raw_status in ('reserved', 'reservado') else (
                    'paused' if raw_status in ('paused', 'pausado') else 'unpublished')))
        values = {
            'name': self._value(row, 'title', 'name', 'reference') or ('Vehículo %s' % external_id),
            'external_id': external_id,
            'connection_id': self.id,
            'source': source,
            'status': status,
            'external_status': raw_status or status,
            'brand': self._value(row, 'brand', 'make', 'marca'),
            'model': self._value(row, 'model', 'modelo'),
            'version': self._value(row, 'version', 'trim', 'versión'),
            'year': int(self._number(self._value(row, 'year', 'model_year', 'anio'))),
            'mileage': self._number(self._value(row, 'mileage', 'km', 'kilometraje')),
            'price': self._number(self._value(row, 'price', 'amount', 'precio')),
            'currency': self._value(row, 'currency', 'currency_code', 'moneda') or 'USD',
            'location': self._value(row, 'location', 'city', 'ciudad'),
            'url': self._value(row, 'url', 'link', 'permalink'),
            'image_url': self._value(row, 'image_url', 'image', 'photo', 'thumbnail'),
            'description': self._value(row, 'description', 'caption', 'details', 'detalle'),
            'raw_payload': json.dumps(row, ensure_ascii=False, default=str),
            'last_seen_at': fields.Datetime.now(),
        }
        listing = Listing.search([('connection_id', '=', self.id), ('external_id', '=', external_id)], limit=1)
        if listing:
            listing.write(values)
        else:
            listing = Listing.create(values)
        return listing

    def action_test_connection(self):
        self.ensure_one()
        if self.demo_mode:
            self.write({'state': 'demo', 'last_error': False})
            return True
        try:
            rows = self._request_rows()
        except Exception as exc:
            self.write({'state': 'error', 'last_error': str(exc)})
            raise
        self.write({
            'state': 'connected', 'last_error': False,
            'last_sync_summary': _('Conexión válida. El feed contiene %s registro(s).') % len(rows),
        })
        return True

    def action_sync(self):
        for connection in self:
            try:
                rows = connection._demo_rows() if connection.demo_mode else connection._request_rows()
                created = updated = 0
                seen_ids = set()
                for row in rows:
                    external_id = str(connection._value(
                        row, 'id', 'external_id', 'vehicle_id', 'listing_id') or '').strip()
                    if external_id:
                        seen_ids.add(external_id)
                    existing = self.env['marketing.vehicle.listing'].search([
                        ('connection_id', '=', connection.id),
                        ('external_id', '=', external_id),
                    ], limit=1)
                    listing = connection._upsert_row(row, source='demo' if connection.demo_mode else 'patiotuerca')
                    if listing:
                        updated += 1 if existing else 0
                        created += 0 if existing else 1
                missing = self.env['marketing.vehicle.listing']
                if connection.mark_missing_unpublished and not connection.demo_mode:
                    missing = self.env['marketing.vehicle.listing'].search([
                        ('connection_id', '=', connection.id), ('active', '=', True),
                        ('external_id', 'not in', list(seen_ids) or ['__none__']),
                        ('status', '=', 'published'),
                    ])
                    missing.write({'status': 'unpublished'})
                summary = _('%s registro(s) procesado(s): %s nuevo(s), %s actualizado(s).') % (
                    len(rows), created, updated)
                if missing:
                    summary += _('%s anuncio(s) ausente(s) se marcaron como despublicados.') % len(missing)
                connection.write({
                    'state': 'demo' if connection.demo_mode else 'connected',
                    'last_sync_at': fields.Datetime.now(), 'last_error': False,
                    'last_sync_summary': summary,
                })
                connection.message_post(body=connection.last_sync_summary)
            except Exception as exc:
                connection.write({'state': 'error', 'last_error': str(exc), 'last_sync_at': fields.Datetime.now()})
                raise
        return True

    def _demo_rows(self):
        return [
            {'id': 'PT-DEMO-001', 'title': 'Chevrolet Tracker Premier', 'status': 'published', 'brand': 'Chevrolet', 'model': 'Tracker', 'version': 'Premier', 'year': 2024, 'mileage': 18000, 'price': 24900, 'currency': 'USD', 'location': 'Quito', 'description': 'SUV publicada para pruebas de catálogo.', 'image_url': 'https://images.unsplash.com/photo-1553440569-bcc63803a83d?auto=format&fit=crop&w=900&q=80'},
            {'id': 'PT-DEMO-002', 'title': 'Kia Sportage LX', 'status': 'published', 'brand': 'Kia', 'model': 'Sportage', 'version': 'LX', 'year': 2023, 'mileage': 26000, 'price': 28900, 'currency': 'USD', 'location': 'Guayaquil', 'description': 'SUV publicada para pruebas de catálogo.', 'image_url': 'https://images.unsplash.com/photo-1542282088-fe8426682b8f?auto=format&fit=crop&w=900&q=80'},
            {'id': 'PT-DEMO-003', 'title': 'Toyota Hilux 4x4', 'status': 'unpublished', 'brand': 'Toyota', 'model': 'Hilux', 'version': '4x4', 'year': 2022, 'mileage': 41000, 'price': 33700, 'currency': 'USD', 'location': 'Cuenca', 'description': 'Registro despublicado para probar filtros y control de inventario.'},
            {'id': 'PT-DEMO-004', 'title': 'Hyundai Tucson', 'status': 'sold', 'brand': 'Hyundai', 'model': 'Tucson', 'version': 'Limited', 'year': 2021, 'mileage': 52000, 'price': 21900, 'currency': 'USD', 'location': 'Manta', 'description': 'Registro vendido conservado en histórico.'},
        ]

    def action_load_demo(self):
        for connection in self:
            connection.demo_mode = True
            connection.action_sync()
        return True

    def action_open_listings(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _('Vehículos del catálogo'),
            'res_model': 'marketing.vehicle.listing', 'view_mode': 'kanban,list,form',
            'domain': [('connection_id', '=', self.id)],
        }


class MarketingVehicleListing(models.Model):
    _name = 'marketing.vehicle.listing'
    _description = 'Vehículo del catálogo externo'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'status, write_date desc, id desc'

    name = fields.Char(string='Vehículo', required=True, tracking=True)
    external_id = fields.Char(string='ID externo', required=True, index=True, tracking=True)
    connection_id = fields.Many2one('marketing.patiotuerca.connection', string='Conexión', required=True, ondelete='cascade', index=True)
    source = fields.Selection([('patiotuerca', 'Patiotuerca'), ('demo', 'Demo'), ('manual', 'Manual')], string='Origen', default='manual', required=True)
    status = fields.Selection([
        ('published', 'Publicado'), ('unpublished', 'Despublicado'),
        ('paused', 'Pausado'), ('reserved', 'Reservado'), ('sold', 'Vendido'),
    ], string='Estado de publicación', default='unpublished', required=True, tracking=True, index=True)
    external_status = fields.Char(string='Estado externo')
    brand = fields.Char(string='Marca')
    model = fields.Char(string='Modelo')
    version = fields.Char(string='Versión')
    year = fields.Integer(string='Año')
    mileage = fields.Float(string='Kilometraje')
    price = fields.Float(string='Precio')
    currency = fields.Char(string='Moneda', default='USD')
    location = fields.Char(string='Ubicación')
    url = fields.Char(string='Enlace externo')
    image_url = fields.Char(string='Imagen')
    description = fields.Text(string='Descripción')
    published_at = fields.Datetime(string='Publicado el')
    unpublished_at = fields.Datetime(string='Despublicado el')
    last_seen_at = fields.Datetime(string='Visto en última sincronización', readonly=True)
    is_stale = fields.Boolean(
        string='Sin actualizar', compute='_compute_freshness', search='_search_is_stale')
    freshness_label = fields.Char(string='Vigencia del dato', compute='_compute_freshness')
    raw_payload = fields.Text(string='Datos recibidos', readonly=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', related='connection_id.company_id', store=True, index=True)

    _external_unique = models.Constraint(
        'unique(connection_id, external_id)', 'El ID externo ya existe en esta conexión.')

    @api.depends('last_seen_at', 'connection_id.stale_after_hours', 'connection_id.last_sync_at')
    def _compute_freshness(self):
        now = fields.Datetime.to_datetime(fields.Datetime.now())
        for record in self:
            seen = fields.Datetime.to_datetime(record.last_seen_at) if record.last_seen_at else False
            stale = not seen or now - seen > timedelta(hours=record.connection_id.stale_after_hours or 48)
            record.is_stale = stale
            record.freshness_label = _('Revisar sincronización') if stale else _('Actualizado')

    def _search_is_stale(self, operator, value):
        if operator not in ('=', '!='):
            return []
        matching = self.search([]).filtered('is_stale')
        if (operator == '=' and value) or (operator == '!=' and not value):
            return [('id', 'in', matching.ids)]
        return [('id', 'not in', matching.ids)]

    def write(self, vals):
        if vals.get('status') == 'published' and 'published_at' not in vals:
            vals['published_at'] = fields.Datetime.now()
        if vals.get('status') in ('unpublished', 'paused', 'reserved', 'sold') and 'unpublished_at' not in vals:
            vals['unpublished_at'] = fields.Datetime.now()
        return super().write(vals)

    def action_open_external(self):
        self.ensure_one()
        if not self.url:
            raise UserError(_('Este vehículo no tiene enlace externo.'))
        return {'type': 'ir.actions.act_url', 'url': self.url, 'target': 'new'}

    def action_mark_published(self):
        self.write({'status': 'published'})
        return True

    def action_mark_unpublished(self):
        self.write({'status': 'unpublished'})
        return True

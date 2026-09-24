import base64
import json
import logging
from datetime import timedelta

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class MarketingCatalogConnection(models.Model):
    _name = 'marketing.catalog.connection'
    _description = 'Conexión de catálogo externo'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'marketing.diagnostic.mixin']
    _order = 'active desc, name'

    name = fields.Char(string='Nombre de la conexión', required=True, tracking=True)
    endpoint_url = fields.Char(
        string='Endpoint del catálogo',
        help='URL del feed JSON o API del catálogo externo. El conector acepta data, items o una lista raíz.')
    api_token = fields.Char(string='Token de acceso', groups='marketing_command_center_catalog.group_catalog_manager')
    feed_file = fields.Binary(
        string='Archivo JSON del catálogo', attachment=True,
        help='Alternativa al endpoint para validar un export del catálogo. Debe contener una lista o data, items, vehicles o listings.')
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
    # Antes se llamaba igual que `listing_ids` y Odoo avisaba en cada
    # arranque de que dos campos del mismo modelo comparten etiqueta.
    listing_count = fields.Integer(compute='_compute_counts', string='Total de vehículos')
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
        Listing = self.env['marketing.vehicle.listing']
        guardadas = self.filtered('id')
        # Contar agrupando en vez de traerse `listing_ids` entero. Abrir la
        # ficha de una conexión con miles de vehículos cargaba los miles en
        # memoria para recorrerlos cuatro veces.
        por_estado = {}
        por_caducidad = {}
        if guardadas:
            for conexion, estado, cuantas in Listing._read_group(
                    [('connection_id', 'in', guardadas.ids)],
                    groupby=['connection_id', 'status'], aggregates=['__count']):
                por_estado.setdefault(conexion.id, {})[estado] = cuantas
            # Los desactualizados, también agrupados: un `search_count` por
            # conexión convertiría la vista de lista en un N+1.
            caducados = Listing._stale_domain(guardadas)
            if caducados:
                por_caducidad = {
                    conexion.id: cuantas
                    for conexion, cuantas in Listing._read_group(
                        caducados, groupby=['connection_id'], aggregates=['__count'])
                }
        for record in self:
            if not record.id:
                # Un registro sin guardar no tiene nada que agrupar, pero sí
                # puede traer líneas en memoria.
                listings = record.listing_ids
                record.listing_count = len(listings)
                record.published_count = len(listings.filtered(
                    lambda item: item.status == 'published'))
                record.unpublished_count = record.listing_count - record.published_count
                record.stale_count = len(listings.filtered('is_stale'))
                continue
            cuentas = por_estado.get(record.id, {})
            record.listing_count = sum(cuentas.values())
            record.published_count = cuentas.get('published', 0)
            record.unpublished_count = record.listing_count - record.published_count
            record.stale_count = por_caducidad.get(record.id, 0)

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

    def _external_id_of(self, row):
        return str(self._value(
            row, 'id', 'external_id', 'vehicle_id', 'listing_id') or '').strip()

    def _row_values(self, row, source='external'):
        """Traduce una fila del feed a valores del anuncio.

        Separado de `_upsert_row` para poder preparar todo el lote antes
        de escribir y crear los nuevos de una sola vez.
        """
        self.ensure_one()
        external_id = self._external_id_of(row)
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
        return values

    def _upsert_row(self, row, source='external', known=None):
        """Escribe o crea un anuncio suelto.

        La sincronización completa usa `_sync_one`, que prepara el lote
        entero. Este método se conserva para tratar una fila aislada.
        """
        Listing = self.env['marketing.vehicle.listing']
        values = self._row_values(row, source)
        if not values:
            return False
        external_id = values['external_id']
        # `known` es el indice que arma la sincronizacion de una sola vez;
        # sin el se busca, para que llamar a este metodo suelto funcione.
        if known is not None:
            listing = known.get(external_id, Listing)
        else:
            listing = Listing.search([
                ('connection_id', '=', self.id), ('external_id', '=', external_id),
            ], limit=1)
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
            self._persist_diagnostic({'state': 'error', 'last_error': str(exc)})
            raise
        self.write({
            'state': 'connected', 'last_error': False,
            'last_sync_summary': _('Conexión válida. El feed contiene %s registro(s).') % len(rows),
        })
        return True

    def _sync_one(self):
        """Sincroniza esta conexión. Las incidencias las trata `action_sync`."""
        self.ensure_one()
        Listing = self.env['marketing.vehicle.listing']
        rows = self._demo_rows() if self.demo_mode else self._request_rows()
        source = 'demo' if self.demo_mode else 'external'
        # Un indice de lo que ya existe, en UNA consulta. Antes se buscaba
        # dos veces por vehiculo: sincronizar 500 anuncios eran 1.000
        # SELECT antes de escribir nada.
        known = {
            listing.external_id: listing
            for listing in Listing.search([('connection_id', '=', self.id)])
        }
        updated = 0
        # Los nuevos van a un diccionario, no a una lista: si el feed trae
        # dos veces el mismo id, antes se intentaban crear dos filas y
        # saltaba la restricción de unicidad, que tumbaba la sincronización
        # entera por un duplicado del proveedor. Ahora gana la última, que
        # es lo que hacía el feed cuando el anuncio ya existía.
        nuevos = {}
        # Los que vienen EN ESTE feed, que no son los mismos que los que ya
        # había guardados: de esa diferencia salen los ausentes.
        seen_ids = set()
        for row in rows:
            values = self._row_values(row, source)
            if not values:
                continue
            external_id = values['external_id']
            seen_ids.add(external_id)
            listing = known.get(external_id)
            if listing:
                listing.write(values)
                updated += 1
            else:
                nuevos[external_id] = values
        if nuevos:
            # Una sola creación para todo el lote, en vez de un INSERT
            # suelto por vehículo.
            Listing.create(list(nuevos.values()))

        missing = Listing.browse()
        if self.mark_missing_unpublished and not self.demo_mode:
            missing = Listing.search([
                ('connection_id', '=', self.id), ('active', '=', True),
                ('external_id', 'not in', list(seen_ids) or ['__none__']),
                ('status', '=', 'published'),
            ])
            missing.write({'status': 'unpublished'})
        summary = _('%s registro(s) procesado(s): %s nuevo(s), %s actualizado(s).') % (
            len(rows), len(nuevos), updated)
        if missing:
            summary += _('%s anuncio(s) ausente(s) se marcaron como despublicados.') % len(missing)
        self.write({
            'state': 'demo' if self.demo_mode else 'connected',
            'last_sync_at': fields.Datetime.now(), 'last_error': False,
            'last_sync_summary': summary,
        })
        self.message_post(body=self.last_sync_summary)
        return True

    def action_sync(self):
        for connection in self:
            try:
                # Un savepoint por conexión, no `cr.rollback()`.
                #
                # El rollback deshacía la transacción ENTERA: con varias
                # conexiones seleccionadas se llevaba por delante lo que ya
                # habían sincronizado las anteriores, y con una sola
                # borraba el `demo_mode = True` que `action_load_demo`
                # acababa de escribir, así que el usuario pulsaba «Cargar
                # demo» y el modo no se quedaba puesto. Después hacía
                # `cr.commit()` a mitad de petición, confirmando ese estado
                # parcial. El savepoint descarta la sincronización a medias
                # de ESTA conexión y nada más.
                with self.env.cr.savepoint():
                    connection._sync_one()
            except Exception as exc:
                # El `raise` deshace la transacción, y con ella cualquier
                # rastro del intento. El diagnóstico se escribe desde una
                # transacción propia para que sobreviva.
                #
                # Antes este camino entero se saltaba durante las pruebas,
                # así que lo único que corría en producción era justo lo
                # que nadie comprobaba.
                connection._persist_diagnostic({
                    'state': 'error', 'last_error': str(exc)[:2000],
                    'last_sync_at': fields.Datetime.now(),
                })
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
    _inherit = ['mail.thread', 'mail.activity.mixin', 'marketing.diagnostic.mixin']
    _order = 'status, write_date desc, id desc'

    name = fields.Char(string='Vehículo', required=True, tracking=True)
    external_id = fields.Char(string='ID externo', required=True, index=True, tracking=True)
    connection_id = fields.Many2one('marketing.catalog.connection', string='Conexión', required=True, ondelete='cascade', index=True)
    # 'patiotuerca' se conserva porque hay filas guardadas con ese valor
    # en las bases donde el modulo se llamaba asi; quitarlo las dejaria
    # con un origen que la seleccion ya no reconoce. Lo que importan los
    # feeds nuevos es 'external', que no ata el modulo a ningun portal.
    source = fields.Selection([('external', 'Catálogo externo'), ('patiotuerca', 'Patiotuerca'), ('demo', 'Demo'), ('manual', 'Manual')], string='Origen', default='manual', required=True)
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
        """Filtro de anuncios desactualizados.

        Odoo normaliza `=` a `in` con un OrderedSet, asi que la guarda
        `operator not in ('=', '!=')` se cumplia SIEMPRE y el metodo salia
        devolviendo un dominio vacio: filtrar por "revisar sincronizacion"
        mostraba todos los anuncios, y filtrar por lo contrario tambien.
        Ademas un OrderedSet([False]) es verdadero por tener un elemento,
        asi que hay que mirar el contenido y no el contenedor.
        """
        if operator not in ('=', '!=', 'in', 'not in'):
            return [('id', 'in', [])]
        wanted = [value] if isinstance(value, bool) else list(value or [])
        looking_for_true = any(bool(item) for item in wanted)
        positive = (operator in ('=', 'in')) == looking_for_true
        domain = self._stale_domain()
        if not domain:
            return [('id', 'in', [])] if positive else []
        return domain if positive else ['!'] + domain

    @api.model
    def _stale_domain(self, connections=None):
        """Dominio de «sin actualizar», para que filtre Postgres.

        El filtro de la lista hacía `self.search([]).filtered('is_stale')`:
        cargaba en memoria TODOS los anuncios de TODAS las conexiones y
        calculaba la vigencia de cada uno, para acabar quedándose con unos
        pocos.

        Y sí se puede expresar como dominio: un anuncio está
        desactualizado si no tiene fecha de visto, o si esa fecha quedó por
        detrás del corte. El corte depende de `stale_after_hours`, que es
        de la conexión y no del anuncio, así que se arma un trozo por
        conexión y se unen con OR. Las conexiones son pocas; los anuncios,
        muchos.
        """
        if connections is None:
            connections = self.env['marketing.catalog.connection'].sudo().search([])
        now = fields.Datetime.to_datetime(fields.Datetime.now())
        domain = []
        for connection in connections:
            cutoff = now - timedelta(hours=connection.stale_after_hours or 48)
            part = ['&', ('connection_id', '=', connection.id),
                    '|', ('last_seen_at', '=', False), ('last_seen_at', '<', cutoff)]
            domain = (['|'] + domain + part) if domain else part
        return domain

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

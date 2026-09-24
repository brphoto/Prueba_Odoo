from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestMarketingCatalogConnection(TransactionCase):
    """El módulo no tenía tests. El filtro de anuncios desactualizados
    devolvía TODOS los registros tanto al pedir los caducados como al
    pedir los frescos, y nadie se enteró."""

    def _demo_connection(self):
        connection = self.env['marketing.catalog.connection'].create({
            'name': 'QA conexión de catálogo', 'demo_mode': True,
        })
        connection.action_load_demo()
        return connection

    def test_stale_filter_splits_the_catalog_in_two(self):
        """`is_stale` tiene que filtrar de verdad, en los dos sentidos.

        Odoo normaliza `=` a `in` con un OrderedSet, así que la guarda
        `operator not in ('=', '!=')` se cumplía siempre y el método salía
        devolviendo un dominio vacío, que en Odoo significa «todo».
        """
        connection = self._demo_connection()
        Listing = self.env['marketing.vehicle.listing']
        listings = Listing.search([('connection_id', '=', connection.id)])
        self.assertTrue(listings, 'El modo demo debería cargar anuncios.')

        # Se fuerza un reparto conocido: la mitad vistos hace mucho.
        old_seen = fields.Datetime.now() - timedelta(hours=500)
        stale_expected = listings[:len(listings) // 2 or 1]
        stale_expected.write({'last_seen_at': old_seen})
        (listings - stale_expected).write({'last_seen_at': fields.Datetime.now()})
        listings.invalidate_recordset()

        by_field = listings.filtered('is_stale')
        self.assertEqual(by_field, stale_expected)

        base = [('connection_id', '=', connection.id)]
        self.assertEqual(
            Listing.search(base + [('is_stale', '=', True)]), stale_expected,
            'Filtrar por desactualizados debería devolver solo esos.')
        self.assertEqual(
            Listing.search(base + [('is_stale', '=', False)]),
            listings - stale_expected,
            'Filtrar por actualizados debería devolver el complemento.')
        self.assertEqual(
            len(Listing.search(base + [('is_stale', '=', True)]))
            + len(Listing.search(base + [('is_stale', '=', False)])),
            len(listings))

    def test_sync_is_idempotent_and_counts_new_versus_updated(self):
        """Sincronizar dos veces no puede duplicar anuncios."""
        connection = self._demo_connection()
        Listing = self.env['marketing.vehicle.listing']
        first = Listing.search_count([('connection_id', '=', connection.id)])
        self.assertTrue(first)

        connection.action_sync()
        second = Listing.search_count([('connection_id', '=', connection.id)])
        self.assertEqual(
            second, first,
            'Una segunda sincronización de las mismas filas no debería crear registros.')
        self.assertIn('actualizado', connection.last_sync_summary)

    def test_upsert_uses_the_prefetched_index(self):
        """El índice evita una búsqueda por vehículo; el resultado es el mismo."""
        connection = self._demo_connection()
        Listing = self.env['marketing.vehicle.listing']
        rows = connection._demo_rows()
        known = {
            listing.external_id: listing
            for listing in Listing.search([('connection_id', '=', connection.id)])
        }
        for row in rows:
            with_index = connection._upsert_row(row, source='demo', known=known)
            without_index = connection._upsert_row(row, source='demo')
            self.assertEqual(
                with_index, without_index,
                'Con y sin índice se tiene que actualizar el mismo anuncio.')

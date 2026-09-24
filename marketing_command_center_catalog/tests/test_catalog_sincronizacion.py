# -*- coding: utf-8 -*-
import base64
import json
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


def _feed(rows):
    """Un feed JSON como el que carga el usuario, sin salir a la red."""
    return base64.b64encode(json.dumps(rows).encode('utf-8'))


@tagged('post_install', '-at_install')
class TestSincronizacionCatalogo(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Conexion = self.env['marketing.catalog.connection']
        self.Anuncio = self.env['marketing.vehicle.listing']

    def _conexion(self, rows=None, **valores):
        datos = {'name': 'QA catálogo', 'feed_filename': 'feed.json'}
        datos.update(valores)
        if rows is not None:
            datos['feed_file'] = _feed(rows)
        return self.Conexion.create(datos)

    def _fila(self, identificador, **extra):
        datos = {'id': identificador, 'title': 'Vehículo %s' % identificador,
                 'status': 'published', 'price': 10000}
        datos.update(extra)
        return datos

    def _anuncios(self, conexion):
        return self.Anuncio.search([('connection_id', '=', conexion.id)])

    # ------------------------------------------------------------------
    # Lo que el feed trae
    # ------------------------------------------------------------------

    def test_a_repeated_id_in_one_feed_does_not_break_the_sync(self):
        """Antes se intentaba crear dos filas con el mismo ID externo y
        saltaba la restricción de unicidad: un duplicado del proveedor
        tumbaba la sincronización entera."""
        conexion = self._conexion([
            self._fila('A-1', title='Primera versión'),
            self._fila('A-2'),
            self._fila('A-1', title='Segunda versión'),
        ])

        conexion.action_sync()

        anuncios = self._anuncios(conexion)
        self.assertEqual(len(anuncios), 2, 'El duplicado creó una fila de más.')
        repetido = anuncios.filtered(lambda a: a.external_id == 'A-1')
        self.assertEqual(
            repetido.name, 'Segunda versión',
            'Con el id repetido debe quedar la última fila del feed, igual '
            'que si hubiera llegado en dos sincronizaciones seguidas.')

    def test_a_row_with_no_id_is_skipped_not_crashed_on(self):
        conexion = self._conexion([
            self._fila('B-1'), {'title': 'Sin identificador'},
        ])

        conexion.action_sync()

        self.assertEqual(len(self._anuncios(conexion)), 1)

    def test_the_summary_separates_new_from_updated(self):
        conexion = self._conexion([self._fila('C-1'), self._fila('C-2')])
        conexion.action_sync()
        self.assertIn('2 nuevo(s)', conexion.last_sync_summary)

        conexion.feed_file = _feed([self._fila('C-1'), self._fila('C-3')])
        conexion.action_sync()

        self.assertIn('1 nuevo(s)', conexion.last_sync_summary)
        self.assertIn('1 actualizado(s)', conexion.last_sync_summary)
        self.assertEqual(len(self._anuncios(conexion)), 3)

    # ------------------------------------------------------------------
    # Ausentes
    # ------------------------------------------------------------------

    def test_a_listing_missing_from_the_feed_is_unpublished_when_asked(self):
        conexion = self._conexion(
            [self._fila('D-1'), self._fila('D-2')],
            mark_missing_unpublished=True)
        conexion.action_sync()

        conexion.feed_file = _feed([self._fila('D-1')])
        conexion.action_sync()

        ausente = self._anuncios(conexion).filtered(
            lambda a: a.external_id == 'D-2')
        self.assertEqual(
            ausente.status, 'unpublished',
            'El anuncio que ya no viene en el feed debería quedar '
            'despublicado con la opción activada.')
        self.assertIn('ausente(s)', conexion.last_sync_summary)

    def test_without_the_option_a_missing_listing_is_left_alone(self):
        """Un feed parcial no puede despublicar medio catálogo."""
        conexion = self._conexion(
            [self._fila('E-1'), self._fila('E-2')],
            mark_missing_unpublished=False)
        conexion.action_sync()

        conexion.feed_file = _feed([self._fila('E-1')])
        conexion.action_sync()

        ausente = self._anuncios(conexion).filtered(
            lambda a: a.external_id == 'E-2')
        self.assertEqual(ausente.status, 'published')

    # ------------------------------------------------------------------
    # El fallo deja rastro
    # ------------------------------------------------------------------

    def _sincronizar_esperando_fallo(self, conexion):
        # A propósito no se usa `assertRaises`: envuelve el bloque en un
        # savepoint y lo deshace, así que se llevaría por delante justo el
        # rastro que esta prueba quiere comprobar.
        try:
            conexion.action_sync()
        except UserError:
            return
        self.fail('La sincronización debería haber fallado.')

    def test_a_failed_sync_leaves_the_reason_on_the_record(self):
        """Este camino no se probaba nunca: el manejo del error estaba
        detrás de un `if not current_test`, así que lo único que corría en
        producción era exactamente lo que ningún test tocaba."""
        conexion = self._conexion()
        conexion.feed_file = base64.b64encode(b'{esto no es json')

        self._sincronizar_esperando_fallo(conexion)

        self.assertEqual(conexion.state, 'error')
        self.assertTrue(
            conexion.last_error,
            'La ficha quedó como si no se hubiera intentado nada.')
        self.assertTrue(conexion.last_sync_at)

    def test_a_failed_sync_does_not_undo_what_came_before_it(self):
        conexion = self._conexion()
        conexion.write({'name': 'Escrito antes de fallar'})
        conexion.feed_file = base64.b64encode(b'no json')

        self._sincronizar_esperando_fallo(conexion)

        self.assertEqual(
            conexion.name, 'Escrito antes de fallar',
            'El manejo del fallo se llevó por delante un cambio anterior.')

    def test_a_feed_without_a_list_explains_itself(self):
        conexion = self._conexion()
        conexion.feed_file = _feed({'total': 3, 'pagina': 1})

        self._sincronizar_esperando_fallo(conexion)

        self.assertIn('lista', conexion.last_error.lower())

    def test_the_half_done_sync_is_discarded(self):
        """El savepoint descarta lo que la sincronización alcanzó a
        escribir antes de reventar; no puede quedar medio catálogo."""
        conexion = self._conexion([self._fila('F-1')])
        conexion.action_sync()
        self.assertEqual(len(self._anuncios(conexion)), 1)

        # Un feed que empieza bien y no llega a ser una lista.
        conexion.feed_file = _feed({'items': 'esto no es una lista'})
        self._sincronizar_esperando_fallo(conexion)

        self.assertEqual(
            len(self._anuncios(conexion)), 1,
            'La sincronización fallida dejó anuncios a medias.')

    # ------------------------------------------------------------------
    # Contadores y vigencia
    # ------------------------------------------------------------------

    def test_the_counters_match_what_was_synced(self):
        conexion = self._conexion([
            self._fila('G-1', status='published'),
            self._fila('G-2', status='published'),
            self._fila('G-3', status='sold'),
        ])
        conexion.action_sync()
        conexion.invalidate_recordset()

        self.assertEqual(conexion.listing_count, 3)
        self.assertEqual(conexion.published_count, 2)
        self.assertEqual(
            conexion.unpublished_count, 1,
            'Todo lo que no está publicado cuenta como despublicado.')

    def test_the_counters_of_two_connections_do_not_mix(self):
        """Se cuentan agrupando; si la agrupación se leyera mal, los
        números de una conexión aparecerían en la otra."""
        primera = self._conexion([self._fila('H-1'), self._fila('H-2')],
                                 name='QA primera')
        segunda = self._conexion([self._fila('H-3')], name='QA segunda')
        (primera | segunda).action_sync()
        (primera | segunda).invalidate_recordset()

        self.assertEqual(primera.listing_count, 2)
        self.assertEqual(segunda.listing_count, 1)

    def test_the_stale_counter_agrees_with_the_filter(self):
        conexion = self._conexion(
            [self._fila('I-%s' % indice) for indice in range(4)],
            stale_after_hours=24)
        conexion.action_sync()
        anuncios = self._anuncios(conexion)
        viejos = anuncios[:2]
        viejos.write({'last_seen_at': fields.Datetime.now() - timedelta(hours=100)})
        (anuncios - viejos).write({'last_seen_at': fields.Datetime.now()})
        conexion.invalidate_recordset()
        anuncios.invalidate_recordset()

        self.assertEqual(conexion.stale_count, 2)
        self.assertEqual(
            self.Anuncio.search([('connection_id', '=', conexion.id),
                                 ('is_stale', '=', True)]),
            viejos,
            'El contador de la ficha y el filtro de la lista tienen que '
            'coincidir: salen del mismo dominio.')

    def test_each_connection_uses_its_own_staleness_window(self):
        """El corte sale de `stale_after_hours`, que es de la conexión. Con
        un solo corte para todas, una de ellas mediría con la ventana
        equivocada."""
        estricta = self._conexion([self._fila('J-1')], name='QA estricta',
                                  stale_after_hours=1)
        amplia = self._conexion([self._fila('J-2')], name='QA amplia',
                                stale_after_hours=720)
        (estricta | amplia).action_sync()
        hace_diez_horas = fields.Datetime.now() - timedelta(hours=10)
        self._anuncios(estricta).write({'last_seen_at': hace_diez_horas})
        self._anuncios(amplia).write({'last_seen_at': hace_diez_horas})
        (estricta | amplia).invalidate_recordset()

        self.assertEqual(
            estricta.stale_count, 1,
            'Con ventana de 1 hora, algo visto hace 10 está desactualizado.')
        self.assertEqual(
            amplia.stale_count, 0,
            'Con ventana de 720 horas, lo mismo sigue vigente.')

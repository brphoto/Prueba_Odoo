from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPosQuote(TransactionCase):
    """Transferencia de pedidos entre cajas.

    El módulo son 2.000 líneas moviendo pedidos (y por tanto dinero) entre
    cajeros, y no tenía ni un solo test. Se cubre aquí lo que rompe de
    forma silenciosa: numeración duplicada, edición de un pedido existente
    y el acuse de recepción.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.env['pos.config'].create({'name': 'QA Caja origen'})
        cls.config_destino = cls.env['pos.config'].create({
            'name': 'QA Caja destino', 'enable_transfer_tracking': True,
        })

    def _quote(self, **values):
        return self.env['pos.quote'].create(dict({
            'name': 'QA pedido',
        }, **values))

    # ------------------------------------------------------------------
    # Numeración
    # ------------------------------------------------------------------

    def test_empty_number_takes_one_from_the_sequence(self):
        quote = self._quote(quote_id='')
        self.assertTrue(
            quote.quote_id,
            'Un pedido sin número debería recibir uno de la secuencia.')

    def test_duplicated_number_is_rejected_on_create(self):
        """Antes solo se comprobaba al escribir.

        Por ahí entraban los números repetidos que luego hacían fallar
        `search_quote` y confundían al cajero que recibe el pedido.
        """
        self._quote(quote_id='QA-DUP-001')
        with self.assertRaises(UserError):
            self._quote(quote_id='QA-DUP-001')

    def test_duplicated_number_inside_the_same_batch_is_rejected(self):
        with self.assertRaises(UserError):
            self.env['pos.quote'].create([
                {'name': 'QA lote 1', 'quote_id': 'QA-LOTE-001'},
                {'name': 'QA lote 2', 'quote_id': 'QA-LOTE-001'},
            ])

    def test_saving_a_quote_with_its_own_number_is_allowed(self):
        """La comprobación de duplicados no puede excluirse a sí misma.

        El formulario reenvía el número en cada guardado; si la búsqueda
        no descarta el propio registro, encuentra ese mismo pedido y no
        deja editarlo nunca.
        """
        quote = self._quote(quote_id='QA-PROPIO-001')
        quote.write({'quote_id': 'QA-PROPIO-001', 'note': 'Editado'})
        self.assertEqual(quote.note, 'Editado')

    def test_number_of_another_quote_is_still_rejected_on_write(self):
        self._quote(quote_id='QA-OTRO-001')
        segundo = self._quote(quote_id='QA-OTRO-002')
        with self.assertRaises(UserError):
            segundo.write({'quote_id': 'QA-OTRO-001'})

    # ------------------------------------------------------------------
    # Importes que llegan del TPV como texto
    # ------------------------------------------------------------------

    def test_amounts_arriving_as_text_are_converted(self):
        """El TPV manda los totales como cadena con separador de miles."""
        quote = self._quote(
            quote_id='QA-IMPORTE-001',
            amount_total='1,234.50', amount_tax='134.50')
        self.assertAlmostEqual(quote.amount_total, 1234.50, places=2)
        self.assertAlmostEqual(quote.amount_tax, 134.50, places=2)

    # ------------------------------------------------------------------
    # Búsqueda y acuse de recepción
    # ------------------------------------------------------------------

    def test_search_quote_finds_an_existing_number(self):
        self._quote(quote_id='QA-BUSCA-001')
        self.assertTrue(
            self.env['pos.quote'].search_quote({'quotation_id': 'QA-BUSCA-001'}))
        self.assertFalse(
            self.env['pos.quote'].search_quote({'quotation_id': 'QA-NO-EXISTE'}))

    def test_mark_received_records_who_took_the_order(self):
        session = self.env['pos.session'].create({
            'config_id': self.config_destino.id})
        quote = self._quote(
            quote_id='QA-RECIBE-001', to_session_id=session.id)
        cajero = self.env['res.users'].create({
            'name': 'QA cajero receptor', 'login': 'qa_cajero_receptor',
        })
        self.assertTrue(self.env['pos.quote'].mark_received(
            quote.id, user_id=cajero.id, cashier_name='QA cajero receptor'))
        quote.invalidate_recordset()
        self.assertEqual(quote.received_user_id, cajero)
        self.assertEqual(quote.received_cashier_name, 'QA cajero receptor')
        self.assertTrue(quote.received_at)

    def test_mark_received_does_nothing_without_tracking_enabled(self):
        """Si la caja destino no lleva trazabilidad, no se inventa un acuse."""
        self.config.enable_transfer_tracking = False
        session = self.env['pos.session'].create({'config_id': self.config.id})
        quote = self._quote(
            quote_id='QA-RECIBE-002', to_session_id=session.id)
        self.assertFalse(self.env['pos.quote'].mark_received(quote.id))
        quote.invalidate_recordset()
        self.assertFalse(quote.received_at)

    def test_mark_received_on_a_missing_quote_does_not_explode(self):
        self.assertFalse(self.env['pos.quote'].mark_received(999999999))

    # ------------------------------------------------------------------
    # Contadores de la sesión
    # ------------------------------------------------------------------

    def test_session_transfer_counters_are_computed_in_batch(self):
        """Los contadores agrupados dan lo mismo que contar a mano.

        Antes eran dos `search_count` por sesión, en cada fila de la lista.
        """
        origen = self.env['pos.session'].create({'config_id': self.config.id})
        destino = self.env['pos.session'].create({
            'config_id': self.config_destino.id})
        for index in range(3):
            self._quote(
                quote_id='QA-CONT-%s' % index,
                session_id=origen.id, to_session_id=destino.id)
        sessions = origen | destino
        sessions.invalidate_recordset()
        self.assertEqual(origen.transfer_sent_count, 3)
        self.assertEqual(origen.transfer_received_count, 0)
        self.assertEqual(destino.transfer_sent_count, 0)
        self.assertEqual(destino.transfer_received_count, 3)

    def test_transfer_tracking_is_enabled_by_default(self):
        """La trazabilidad viene activada de fabrica.

        Importa porque `mark_received` no registra nada cuando esta
        apagada: si el valor por defecto cambiara, los acuses de
        recepcion dejarian de guardarse sin que nadie lo note.
        """
        config = self.env['pos.config'].create({'name': 'QA caja por defecto'})
        self.assertTrue(config.enable_transfer_tracking)

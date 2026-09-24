# -*- coding: utf-8 -*-
from datetime import date, timedelta

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestCortePercentil(TransactionCase):
    """El corte A/B/C reparte la cartera por proporciones de Pareto.

    Es lo que decide en qué categoría cae cada cliente, y de ahí salen
    las listas de envío, las alertas y los paneles. Era lógica pura sin
    una sola prueba.
    """

    def setUp(self):
        super().setUp()
        self.Partner = self.env['res.partner']

    def _filas(self, cuantas):
        """Puntuaciones descendentes y distintas, para que el orden no
        dependa de desempates."""
        return [{'score': 100 - indice} for indice in range(cuantas)]

    def _reparto(self, filas):
        cuenta = {}
        for fila in filas:
            cuenta[fila['category']] = cuenta.get(fila['category'], 0) + 1
        return cuenta

    # ------------------------------------------------------------------

    def test_ten_customers_split_two_three_five(self):
        """20% / 30% / 50% sobre diez da exactamente 2, 3 y 5."""
        filas = self._filas(10)

        self.Partner._assign_percentile_categories(filas)

        self.assertEqual(self._reparto(filas), {'a': 2, 'b': 3, 'c': 5})

    def test_the_best_scores_go_to_the_top_category(self):
        filas = self._filas(10)

        self.Partner._assign_percentile_categories(filas)

        de_a = [f['score'] for f in filas if f['category'] == 'a']
        de_c = [f['score'] for f in filas if f['category'] == 'c']
        self.assertGreater(
            min(de_a), max(de_c),
            'Un cliente de categoría C quedó por encima de uno de A.')

    def test_a_single_customer_does_not_end_up_uncategorised(self):
        """Con una cartera de uno, el 20% redondea a cero. Sin la guarda
        del mínimo, ese cliente se quedaba sin categoría."""
        filas = self._filas(1)

        self.Partner._assign_percentile_categories(filas)

        self.assertEqual(filas[0]['category'], 'a')

    def test_two_customers_fill_a_and_b(self):
        filas = self._filas(2)

        self.Partner._assign_percentile_categories(filas)

        self.assertEqual(self._reparto(filas), {'a': 1, 'b': 1})

    def test_everyone_gets_a_category(self):
        """Ninguna cartera puede dejar filas sin clasificar."""
        for cuantas in (1, 2, 3, 5, 7, 11, 100):
            filas = self._filas(cuantas)
            self.Partner._assign_percentile_categories(filas)
            self.assertEqual(
                sum(self._reparto(filas).values()), cuantas,
                'Con %s clientes quedaron filas sin categoría.' % cuantas)

    def test_it_uses_the_catalogue_codes_not_the_letters_abc(self):
        """La documentación promete que si el usuario recodifica sus
        categorías, el corte usa los códigos que existen de verdad. Sin
        esto se escribían literales 'a'/'b'/'c' que podían no
        corresponder a ningún registro."""
        Segmento = self.env['crm.rfm.segment']
        Segmento.search([('definition_type', '=', 'category')]).write(
            {'active': False})
        for codigo, secuencia in (('oro', 10), ('plata', 20), ('bronce', 30)):
            Segmento.create({
                'name': codigo.title(), 'code': codigo,
                'definition_type': 'category', 'sequence': secuencia,
            })
        filas = self._filas(10)

        self.Partner._assign_percentile_categories(filas)

        self.assertEqual(
            set(self._reparto(filas)), {'oro', 'plata', 'bronce'},
            'El corte siguió escribiendo las letras por defecto en vez de '
            'los códigos configurados.')


@tagged('post_install', '-at_install')
class TestCortePorUmbral(TransactionCase):

    def test_the_configured_thresholds_win(self):
        filas = [{'score': 85}, {'score': 50}, {'score': 10}]

        self.env['res.partner']._assign_threshold_categories(filas)

        self.assertEqual([f['category'] for f in filas], ['a', 'b', 'c'])

    def test_with_no_catalogue_it_falls_back_to_70_and_40(self):
        """Si alguien desactiva todas las categorías, el reparto no puede
        quedarse en blanco."""
        self.env['crm.rfm.segment'].search(
            [('definition_type', '=', 'category')]).write({'active': False})
        filas = [{'score': 70}, {'score': 69}, {'score': 40}, {'score': 39}]

        self.env['res.partner']._assign_threshold_categories(filas)

        self.assertEqual(
            [f['category'] for f in filas], ['a', 'b', 'b', 'c'],
            'Los umbrales de respaldo son 70 y 40, y ambos son inclusivos.')

    def test_a_score_outside_every_range_still_gets_a_category(self):
        self.env['crm.rfm.segment'].search(
            [('definition_type', '=', 'category')]).write(
                {'score_min': 90, 'score_max': 95})
        filas = [{'score': 20}]

        self.env['res.partner']._assign_threshold_categories(filas)

        self.assertTrue(filas[0].get('category'))


@tagged('post_install', '-at_install')
class TestFusionDeFuentes(TransactionCase):
    """`_merge_rfm_rows` suma la facturación de otra fuente sobre la
    nativa. Si se equivoca, un cliente cambia de categoría."""

    def setUp(self):
        super().setUp()
        self.Partner = self.env['res.partner']
        self.hoy = date(2026, 9, 20)
        self.cliente = self.env['res.partner'].create({'name': 'QA fusión'})

    def _nativa(self, total, cuantas, dias):
        fila = {
            'partner': self.cliente, 'total': total, 'count': cuantas,
            'recency_days': dias,
            'last_date': self.hoy - timedelta(days=dias),
        }
        return [fila], {self.cliente.id: fila}

    def test_the_totals_of_both_sources_add_up(self):
        filas, por_cliente = self._nativa(1000.0, 4, 30)

        self.Partner._merge_rfm_rows(filas, por_cliente, {
            self.cliente.id: {
                'partner': self.cliente, 'total': 500.0, 'count': 2,
                'last_date': self.hoy - timedelta(days=90)},
        }, self.hoy)

        self.assertEqual(filas[0]['total'], 1500.0)
        self.assertEqual(filas[0]['count'], 6)

    def test_the_most_recent_date_wins(self):
        """La recencia es la de la compra más reciente, venga de donde
        venga. Quedarse con la de la fuente externa envejecería al
        cliente sin motivo."""
        filas, por_cliente = self._nativa(1000.0, 4, 30)

        self.Partner._merge_rfm_rows(filas, por_cliente, {
            self.cliente.id: {
                'partner': self.cliente, 'total': 500.0, 'count': 2,
                'last_date': self.hoy - timedelta(days=5)},
        }, self.hoy)

        self.assertEqual(filas[0]['recency_days'], 5)
        self.assertEqual(filas[0]['last_date'], self.hoy - timedelta(days=5))

    def test_an_older_external_date_does_not_age_the_customer(self):
        filas, por_cliente = self._nativa(1000.0, 4, 30)

        self.Partner._merge_rfm_rows(filas, por_cliente, {
            self.cliente.id: {
                'partner': self.cliente, 'total': 500.0, 'count': 2,
                'last_date': self.hoy - timedelta(days=200)},
        }, self.hoy)

        self.assertEqual(filas[0]['recency_days'], 30)

    def test_a_customer_only_in_the_other_source_is_added(self):
        filas, por_cliente = [], {}
        otro = self.env['res.partner'].create({'name': 'QA solo externo'})

        self.Partner._merge_rfm_rows(filas, por_cliente, {
            otro.id: {'partner': otro, 'total': 800.0, 'count': 3,
                      'last_date': self.hoy - timedelta(days=12)},
        }, self.hoy)

        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0]['total'], 800.0)
        self.assertEqual(filas[0]['recency_days'], 12)

    def test_a_zero_total_is_ignored(self):
        """Una fila sin facturación no puede crear un cliente en la
        clasificación ni ensuciar su recencia."""
        filas, por_cliente = [], {}
        otro = self.env['res.partner'].create({'name': 'QA sin importe'})

        self.Partner._merge_rfm_rows(filas, por_cliente, {
            otro.id: {'partner': otro, 'total': 0.0, 'count': 5,
                      'last_date': self.hoy},
        }, self.hoy)

        self.assertEqual(filas, [])

    def test_an_entry_without_partner_is_ignored(self):
        filas, por_cliente = [], {}

        self.Partner._merge_rfm_rows(filas, por_cliente, {
            999999: {'partner': False, 'total': 300.0, 'count': 1,
                     'last_date': self.hoy},
        }, self.hoy)

        self.assertEqual(filas, [])

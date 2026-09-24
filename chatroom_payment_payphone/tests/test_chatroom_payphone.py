from unittest.mock import patch

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged

PROVIDER = ('odoo.addons.payment_payphone.models.payment_provider'
            '.PaymentProvider._payphone_create_link')


@tagged('post_install', '-at_install')
class TestChatroomPayPhone(TransactionCase):
    """Envío de enlaces de cobro PayPhone desde el chatroom.

    Este módulo es la bisagra entre dos stacks: decide si un documento se
    cobra por PayPhone o cae al enlace genérico de Odoo. Un error aquí no
    da un fallo visible, le manda al cliente un enlace equivocado. Nunca
    tuvo tests. Lo que se cubre es esa decisión y el rastro que deja.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls.env.ref('payment_payphone.payment_provider_payphone')
        cls.provider.write({
            'state': 'test',
            'payphone_flow': 'link',
            'payphone_token': 'qa-token',
            'payphone_store_id': 'qa-store',
            'company_id': cls.env.company.id,
        })
        cls.provider.with_context(active_test=False).payment_method_ids.filtered(
            lambda method: method.code == 'payphone_link'
        ).active = True
        cls.partner = cls.env['res.partner'].create({'name': 'Cliente PayPhone'})
        cls.channel = cls.env['chatroom.channel'].create({
            'channel_type': 'whatsapp',
            'external_id': '593999000111',
            'partner_id': cls.partner.id,
        })
        product = cls.env['product.product'].create({
            'name': 'Servicio QA',
            'type': 'service',
            'list_price': 25.0,
        })
        cls.order = cls.env['sale.order'].create({
            'partner_id': cls.partner.id,
            'order_line': [(0, 0, {'product_id': product.id, 'product_uom_qty': 1})],
        })
        cls.order.action_confirm()

    def _mute_send(self, sink=None):
        """Silencia el envío real del mensaje al cliente."""
        return patch.object(
            type(self.channel), 'action_send_text',
            side_effect=lambda body: sink.append(body) if sink is not None else None)

    def _send(self, link='https://pay.payphonetodoesposible.com/qa'):
        enviados = []
        with patch(PROVIDER, return_value=link), self._mute_send(enviados):
            self.channel.action_send_payment_link('sale.order', self.order.id)
        return enviados

    def _last_history(self):
        return self.env['chatroom.payment.link'].search(
            [('channel_id', '=', self.channel.id)], order='id desc', limit=1)

    # ------------------------------------------------------------------
    # La decisión: PayPhone o el enlace genérico
    # ------------------------------------------------------------------

    def test_a_confirmed_order_is_charged_through_payphone(self):
        enviados = self._send()
        self.assertEqual(len(enviados), 1)
        self.assertIn('pay.payphonetodoesposible.com', enviados[0])

    def test_the_link_creates_a_transaction_for_the_order(self):
        """Sin transacción no hay forma de conciliar el cobro después."""
        self._send()
        history = self._last_history()
        self.assertEqual(history.provider_id, self.provider)
        self.assertTrue(history.transaction_id,
                        'El enlace de PayPhone debe quedar ligado a su transacción.')
        self.assertEqual(history.transaction_id.sale_order_ids, self.order)
        self.assertEqual(history.transaction_id.partner_id, self.partner)
        self.assertAlmostEqual(history.transaction_id.amount,
                               self.order.amount_total, places=2)

    def test_the_history_entry_is_marked_as_sent(self):
        self._send()
        history = self._last_history()
        self.assertEqual(history.state, 'sent')
        self.assertTrue(history.sent_at)
        self.assertEqual(history.res_model, 'sale.order')
        self.assertEqual(history.res_id, self.order.id)

    def test_a_disabled_provider_falls_back_to_the_generic_link(self):
        """Si PayPhone no está operativo el cobro no puede quedar mudo:
        tiene que salir por el enlace genérico de Odoo."""
        self.provider.state = 'disabled'
        with patch(PROVIDER) as payphone, self._mute_send():
            try:
                self.channel.action_send_payment_link('sale.order', self.order.id)
            except UserError:
                pass  # La BD de test no tiene otro proveedor en línea.
        payphone.assert_not_called()

    def test_another_provider_chosen_by_hand_is_respected(self):
        """El agente puede elegir proveedor en la vista. Si elige uno que
        no es PayPhone, este módulo no debe secuestrar el cobro."""
        otro = self.env['payment.provider'].search(
            [('code', '!=', 'payphone')], limit=1)
        self.assertTrue(otro, 'Se necesita otro proveedor para esta prueba.')
        with patch(PROVIDER) as payphone, self._mute_send():
            try:
                self.channel.with_context(
                    chatroom_payment_provider_id=otro.id
                ).action_send_payment_link('sale.order', self.order.id)
            except UserError:
                pass
        payphone.assert_not_called()

    # ------------------------------------------------------------------
    # Lo que no se debe cobrar
    # ------------------------------------------------------------------

    def test_an_order_with_nothing_pending_is_refused(self):
        """Cobrar cero es peor que no cobrar: el cliente recibe un enlace
        que no puede pagar."""
        vacia = self.env['sale.order'].create({'partner_id': self.partner.id})
        with self.assertRaises(ValidationError):
            self.provider._chatroom_create_payment_link(vacia)

    def test_a_document_without_payment_support_is_refused(self):
        with self.assertRaises(ValidationError):
            self.provider._chatroom_create_payment_link(self.partner)

    def test_a_provider_not_set_to_link_flow_is_refused(self):
        self.provider.payphone_flow = 'box'
        with self.assertRaises(ValidationError):
            self.provider._chatroom_create_payment_link(self.order)

    def test_an_empty_link_raises_a_readable_error(self):
        """`UserError` no estaba importado en el módulo: este camino
        reventaba con un `NameError` en vez del mensaje al agente."""
        with patch(PROVIDER, return_value=''), self._mute_send():
            with self.assertRaises(UserError):
                self.channel.action_send_payment_link('sale.order', self.order.id)

    def test_each_link_gets_its_own_reference(self):
        """Dos enlaces del mismo pedido no pueden compartir referencia o
        PayPhone rechaza el segundo por duplicado."""
        self._send()
        self._send()
        historial = self.env['chatroom.payment.link'].search(
            [('channel_id', '=', self.channel.id)], order='id desc', limit=2)
        referencias = historial.transaction_id.mapped('reference')
        self.assertEqual(len(set(referencias)), 2)
        for referencia in referencias:
            self.assertTrue(
                referencia.startswith('CHAT-SALE-ORDER-%s-' % self.order.id),
                'Referencia inesperada: %s' % referencia)

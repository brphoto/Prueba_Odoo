from unittest.mock import patch

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestDiagnosticoChatroom(TransactionCase):
    """El rastro de un fallo tiene que sobrevivir al fallo.

    En Odoo una excepción deshace la transacción entera, así que escribir
    el error y acto seguido relanzar lo pierde siempre. Hay dos casos
    distintos y el mixin trata cada uno de una forma:

    - El registro ya existía: se reescribe desde otra transacción.
    - El registro se creó en la operación que falla: el rollback se lo
      lleva entero, así que hay que volver a crearlo aparte.
    """

    def test_the_models_that_report_errors_have_the_helpers(self):
        for nombre in ('chatroom.channel', 'chatroom.payment.link'):
            modelo = self.env[nombre]
            self.assertTrue(hasattr(modelo, '_persist_diagnostic'),
                            '%s se quedó sin el ayudante.' % nombre)
            self.assertTrue(hasattr(modelo, '_persist_diagnostic_record'),
                            '%s se quedó sin el ayudante de creación.' % nombre)

    def test_rewriting_an_existing_record(self):
        canal = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp', 'external_id': '593999000900',
        })
        canal._persist_diagnostic({'state': 'closed'})
        self.assertEqual(canal.state, 'closed')

    def test_an_empty_recordset_is_harmless(self):
        """Se llama desde un `except`, donde el registro puede haberse
        quedado por el camino."""
        self.env['chatroom.channel']._persist_diagnostic({'state': 'closed'})

    def test_creating_the_trace_record(self):
        """Para cuando lo que se pierde no es un campo sino el registro
        entero: el historial de un enlace de pago que no llegó a salir."""
        canal = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp', 'external_id': '593999000901',
        })
        nuevo_id = canal._persist_diagnostic_record('chatroom.payment.link', {
            'name': 'Enlace QA',
            'channel_id': canal.id,
            'link': 'https://ejemplo.invalid/pago',
            'state': 'error',
            'error_message': 'no se pudo enviar',
        })
        self.assertTrue(nuevo_id)
        rastro = self.env['chatroom.payment.link'].browse(nuevo_id)
        self.assertEqual(rastro.state, 'error')
        self.assertEqual(rastro.error_message, 'no se pudo enviar')
        self.assertEqual(rastro.link, 'https://ejemplo.invalid/pago',
                         'El enlace no puede perderse: es el dato que explica '
                         'qué se intentó enviar.')

    def test_in_tests_neither_helper_opens_another_transaction(self):
        """Abrir otra transacción durante un test dejaría datos escritos
        de verdad y el caso siguiente los heredaría."""
        canal = self.env['chatroom.channel'].create({
            'channel_type': 'whatsapp', 'external_id': '593999000902',
        })
        with patch.object(type(self.env.registry), 'cursor') as otro:
            canal._persist_diagnostic({'state': 'closed'})
            canal._persist_diagnostic_record('chatroom.payment.link', {
                'name': 'Enlace QA 2', 'channel_id': canal.id,
                'link': 'https://ejemplo.invalid/2', 'state': 'error',
            })
        otro.assert_not_called()

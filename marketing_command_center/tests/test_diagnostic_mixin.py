from unittest.mock import patch

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestDiagnosticMixin(TransactionCase):
    """El diagnóstico tiene que sobrevivir al fallo que lo provocó.

    El patrón que había repartido por los conectores era escribir el
    motivo del error y acto seguido lanzar una excepción. En Odoo eso
    deshace la transacción entera, así que el motivo se perdía siempre:
    el usuario leía el diálogo, lo cerraba, y la ficha seguía como si
    nunca se hubiera intentado nada.
    """

    def test_every_connector_model_has_the_helper(self):
        """Si un modelo pierde el mixin, vuelve a perder sus errores y no
        hay nada que lo delate hasta que alguien mira una ficha."""
        esperados = [
            'marketing.social.agent.chat',
            'marketing.social.account',
            'marketing.social.publication',
        ]
        for nombre in esperados:
            self.assertTrue(
                hasattr(self.env[nombre], '_persist_diagnostic'),
                '%s se quedó sin el ayudante de diagnóstico.' % nombre)

    def test_the_helper_writes_what_it_is_given(self):
        chat = self.env['marketing.social.agent.chat'].create({'name': 'QA mixin'})
        chat._persist_diagnostic({'state': 'error', 'answer': 'detalle del fallo'})
        self.assertEqual(chat.state, 'error')
        self.assertEqual(chat.answer, 'detalle del fallo')

    def test_an_empty_recordset_is_harmless(self):
        """Se llama desde un `except`, donde el registro puede haberse
        quedado por el camino. No debe añadir un segundo error al
        primero."""
        vacio = self.env['marketing.social.agent.chat']
        vacio._persist_diagnostic({'state': 'error'})

    def test_in_tests_it_does_not_open_another_transaction(self):
        """Abrir otra transacción durante un test dejaría datos escritos
        de verdad en la base y el caso siguiente los heredaría."""
        chat = self.env['marketing.social.agent.chat'].create({'name': 'QA aislamiento'})
        with patch.object(type(self.env.registry), 'cursor') as otro_cursor:
            chat._persist_diagnostic({'state': 'error'})
        otro_cursor.assert_not_called()
        self.assertEqual(chat.state, 'error')

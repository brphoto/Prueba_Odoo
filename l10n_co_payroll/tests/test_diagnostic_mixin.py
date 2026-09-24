from unittest.mock import patch

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestDiagnosticoNomina(TransactionCase):
    """El motivo de un fallo tiene que sobrevivir al fallo.

    El patrón que había por toda la nómina era escribir el error y acto
    seguido relanzar. En Odoo eso deshace la transacción entera, así que
    el motivo se perdía siempre: el usuario leía el diálogo, lo cerraba,
    y la ficha seguía como si no se hubiera intentado nada.
    """

    def test_every_model_that_reports_errors_has_the_helper(self):
        """Si un modelo pierde el mixin vuelve a perder sus diagnósticos,
        y nada lo delata hasta que alguien mira una ficha."""
        for nombre in ("l10n.co.payroll.parameter.import",
                       "l10n.co.payroll.salary.rule",
                       "hr.payslip"):
            self.assertTrue(
                hasattr(self.env[nombre], "_persist_diagnostic"),
                "%s se quedó sin el ayudante de diagnóstico." % nombre)

    def test_the_helper_writes_what_it_is_given(self):
        regla = self.env["l10n.co.payroll.salary.rule"].search([], limit=1)
        if not regla:
            self.skipTest("La base no tiene ninguna regla salarial.")
        regla._persist_diagnostic({
            "validation_state": "error",
            "validation_message": "fórmula inválida",
        })
        self.assertEqual(regla.validation_state, "error")
        self.assertEqual(regla.validation_message, "fórmula inválida")

    def test_the_optional_callback_runs_too(self):
        """La DIAN lo usa para la bitácora de intentos, que se perdía por
        el mismo motivo que el `write`."""
        regla = self.env["l10n.co.payroll.salary.rule"].search([], limit=1)
        if not regla:
            self.skipTest("La base no tiene ninguna regla salarial.")
        recibido = []
        regla._persist_diagnostic(
            {"validation_state": "error"},
            lambda registro: recibido.append(registro))
        self.assertEqual(len(recibido), 1)
        self.assertEqual(recibido[0].id, regla.id)

    def test_an_empty_recordset_is_harmless(self):
        """Se llama desde un `except`, donde el registro puede haberse
        quedado por el camino. No debe añadir un segundo error al
        primero."""
        vacio = self.env["l10n.co.payroll.salary.rule"]
        vacio._persist_diagnostic({"validation_state": "error"})

    def test_in_tests_it_does_not_open_another_transaction(self):
        """Abrir otra transacción durante un test dejaría datos escritos
        de verdad y el caso siguiente los heredaría."""
        regla = self.env["l10n.co.payroll.salary.rule"].search([], limit=1)
        if not regla:
            self.skipTest("La base no tiene ninguna regla salarial.")
        with patch.object(type(self.env.registry), "cursor") as otro:
            regla._persist_diagnostic({"validation_state": "error"})
        otro.assert_not_called()
        self.assertEqual(regla.validation_state, "error")

    # No hay test de recorrido completo por `action_validate_formula`:
    # el `@api.constrains` del modelo rechaza una formula invalida en el
    # propio `create`, asi que nunca llega a existir una regla guardada
    # con formula rota sobre la que pulsar el boton. Lo que si se puede
    # comprobar -y se comprueba arriba- es el ayudante en si.

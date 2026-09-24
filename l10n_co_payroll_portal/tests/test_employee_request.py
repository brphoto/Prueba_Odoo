from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPortalRequest(TransactionCase):
    """Solicitudes del portal del colaborador.

    Este módulo no tenía ningún test y aprobar una solicitud crea cosas
    de verdad: una ausencia en el calendario o una cuenta bancaria nueva
    a la que se le pagará la nómina. Lo que se cubre aquí es que solo se
    apruebe lo que debe aprobarse, y una sola vez.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.empleado = cls.env["hr.employee"].create({"name": "Colaborador QA"})
        cls.responsable = cls.env["res.users"].create({
            "name": "Responsable de nómina QA",
            "login": "qa.nomina.responsable",
            "email": "qa.nomina.responsable@example.invalid",
            "group_ids": [(4, cls.env.ref(
                "l10n_co_payroll.group_co_payroll_manager").id)],
        })

    def _solicitud(self, **valores):
        return self.env["l10n.co.payroll.portal.request"].create(dict({
            "employee_id": self.empleado.id,
            "request_type": "other",
            "description": "Solicitud de prueba",
        }, **valores))

    # ------------------------------------------------------------------
    # Envío
    # ------------------------------------------------------------------

    def test_a_draft_request_can_be_submitted(self):
        solicitud = self._solicitud()
        solicitud.action_submit()
        self.assertEqual(solicitud.state, "submitted")

    def test_a_rejected_request_can_be_submitted_again(self):
        """Rechazar no puede ser un callejón sin salida: el colaborador
        tiene que poder corregir y volver a enviar."""
        solicitud = self._solicitud()
        solicitud.action_submit()
        solicitud.with_user(self.responsable).action_reject()
        solicitud.action_submit()
        self.assertEqual(solicitud.state, "submitted")

    def test_an_approved_request_cannot_be_submitted_again(self):
        """El fallo que estaba abierto.

        `action_submit` escribía «enviada» sin mirar el estado, así que
        una solicitud ya aprobada podía volver atrás y aprobarse otra
        vez. Cada aprobación crea una ausencia o una cuenta bancaria
        nueva, así que era una vía directa a duplicarlas.
        """
        solicitud = self._solicitud()
        solicitud.action_submit()
        solicitud.with_user(self.responsable).action_approve()
        self.assertEqual(solicitud.state, "approved")
        with self.assertRaises(UserError):
            solicitud.action_submit()

    # ------------------------------------------------------------------
    # Quién puede aprobar
    # ------------------------------------------------------------------

    def test_only_a_payroll_manager_approves(self):
        otro = self.env["res.users"].create({
            "name": "Empleado sin permisos QA",
            "login": "qa.nomina.sinpermisos",
            "email": "qa.nomina.sinpermisos@example.invalid",
            "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
        })
        solicitud = self._solicitud()
        solicitud.action_submit()
        with self.assertRaises(UserError):
            solicitud.with_user(otro).action_approve()

    def test_only_submitted_requests_are_approved(self):
        solicitud = self._solicitud()
        with self.assertRaises(UserError):
            solicitud.with_user(self.responsable).action_approve()

    def test_rejecting_records_who_and_when(self):
        """Sin la firma de quién rechazó no hay forma de reclamar."""
        solicitud = self._solicitud()
        solicitud.action_submit()
        solicitud.with_user(self.responsable).action_reject()
        self.assertEqual(solicitud.state, "rejected")
        self.assertEqual(solicitud.reviewed_by, self.responsable)
        self.assertTrue(solicitud.reviewed_at)

    # ------------------------------------------------------------------
    # Validaciones
    # ------------------------------------------------------------------

    def test_a_request_needs_a_description(self):
        with self.assertRaises(ValidationError):
            self._solicitud(description="   ")

    def test_the_dates_must_be_in_order(self):
        from datetime import date
        with self.assertRaises(ValidationError):
            self._solicitud(request_type="vacation",
                            date_from=date(2026, 5, 10),
                            date_to=date(2026, 5, 1))

    def test_a_bank_change_needs_a_usable_account_number(self):
        """Una cuenta con letras o demasiado corta llegaría al banco y el
        pago rebotaría."""
        for numero in ("abc", "12", "12-34", ""):
            with self.assertRaises(ValidationError, msg="Se aceptó %r" % numero):
                self._solicitud(request_type="bank_change",
                                bank_account_number=numero)
        solicitud = self._solicitud(request_type="bank_change",
                                    bank_account_number="1234567890")
        self.assertTrue(solicitud)

    def test_an_advance_needs_a_positive_amount(self):
        with self.assertRaises(ValidationError):
            self._solicitud(request_type="advance", requested_amount=0.0)

    def test_a_loan_needs_at_least_one_installment(self):
        with self.assertRaises(ValidationError):
            self._solicitud(request_type="loan", requested_amount=100.0,
                            installment_count=0)

    def test_the_account_number_is_masked(self):
        """El número completo no debe quedar a la vista en listas ni
        correos: solo los cuatro últimos dígitos."""
        solicitud = self._solicitud(request_type="bank_change",
                                    bank_account_number="1234567890")
        self.assertEqual(solicitud.masked_bank_account, "******7890")

    # ------------------------------------------------------------------
    # Lo que la aprobación crea de verdad
    # ------------------------------------------------------------------

    def test_approving_a_bank_change_needs_a_contact(self):
        """`address_home_id` no existe en Odoo 19; esta rama moría con
        `AttributeError` antes de comprobar nada. El campo del núcleo es
        `work_contact_id`, y es además el que exige el dominio de
        `hr.employee.bank_account_ids`."""
        self.empleado.work_contact_id = False
        solicitud = self._solicitud(request_type="bank_change",
                                    bank_account_number="1234567890")
        solicitud.action_submit()
        with self.assertRaises(UserError):
            solicitud.with_user(self.responsable).action_approve()

    def test_approving_a_bank_change_creates_the_account_for_that_contact(self):
        contacto = self.env["res.partner"].create({"name": "Contacto QA"})
        self.empleado.work_contact_id = contacto
        solicitud = self._solicitud(request_type="bank_change",
                                    bank_account_number="1234 5678 90")
        solicitud.action_submit()
        solicitud.with_user(self.responsable).action_approve()
        self.assertEqual(solicitud.state, "approved")
        cuenta = solicitud.applied_record
        self.assertTrue(cuenta, "La aprobación debe dejar rastro de lo creado.")
        self.assertEqual(cuenta._name, "res.partner.bank")
        self.assertEqual(cuenta.acc_number, "1234567890",
                         "Los espacios del formulario no deben llegar al banco.")
        self.assertEqual(cuenta.partner_id, contacto)

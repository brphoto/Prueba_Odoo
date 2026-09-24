from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged

CANAL = 'odoo.addons.chatroom_whatsapp.models.chatroom_channel.ChatroomChannel'


@tagged('post_install', '-at_install')
class TestNpsWhatsapp(TransactionCase):
    """Campañas NPS enviadas por WhatsApp.

    Este módulo no tenía tests y decide a quién se le manda un mensaje de
    WhatsApp. Equivocarse aquí no da un error visible: escribe a alguien
    que pidió no ser molestado, o deja a media campaña sin enviar.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.plantilla = cls.env['chatroom.template'].create({
            'name': 'nps_qa',
            'language': 'es',
            'status': 'approved',
            'body': 'Hola, cuéntanos qué tal: {{1}}',
        })
        cls.encuesta = cls.env['survey.survey'].search([], limit=1)
        if not cls.encuesta:
            cls.encuesta = cls.env['survey.survey'].create({'title': 'NPS QA'})

    def _campana(self, **valores):
        return self.env['crm.nps.campaign'].create(dict({
            'name': 'Campaña QA',
            'survey_id': self.encuesta.id,
            'channel': 'whatsapp',
            'whatsapp_template_id': self.plantilla.id,
        }, **valores))

    def _destinatario(self, campana, **valores_partner):
        partner = self.env['res.partner'].create(dict({
            'name': 'Cliente NPS QA',
            'phone': '+593999000111',
        }, **valores_partner))
        return self.env['crm.nps.campaign.recipient'].create({
            'campaign_id': campana.id,
            'partner_id': partner.id,
            'survey_url': 'https://ejemplo.invalid/encuesta/1',
        })

    # ------------------------------------------------------------------
    # Configuración de la campaña
    # ------------------------------------------------------------------

    def test_a_whatsapp_campaign_needs_a_template(self):
        """Sin plantilla aprobada Meta rechaza el envío, y la campaña se
        quedaría encolada sin que nadie sepa por qué."""
        with self.assertRaises(ValidationError):
            self._campana(whatsapp_template_id=False)

    def test_the_template_must_have_a_variable_for_the_link(self):
        """La primera variable lleva el enlace de la encuesta. Sin ella
        el cliente recibe un mensaje sin forma de responder."""
        sin_variable = self.env['chatroom.template'].create({
            'name': 'nps_qa_sin_variable', 'language': 'es',
            'status': 'approved', 'body': 'Hola, cuéntanos qué tal.',
        })
        with self.assertRaises(ValidationError):
            self._campana(whatsapp_template_id=sin_variable.id)

    def test_the_both_channel_asks_for_email_and_whatsapp(self):
        campana = self._campana(channel='both')
        self.assertEqual(sorted(campana._requested_channels()),
                         ['email', 'whatsapp'])

    def test_the_whatsapp_channel_does_not_ask_for_email(self):
        self.assertEqual(self._campana()._requested_channels(), ['whatsapp'])

    # ------------------------------------------------------------------
    # A quién NO se le escribe
    # ------------------------------------------------------------------

    def test_a_contact_who_opted_out_is_never_written_to(self):
        """Lo que está en juego aquí es legal, no estético."""
        campana = self._campana()
        linea = self._destinatario(campana, whatsapp_opt_out=True)
        with patch('%s.action_send_template' % CANAL) as enviar:
            campana._send_whatsapp_recipient(linea)
        enviar.assert_not_called()
        self.assertEqual(linea.whatsapp_state, 'skipped')
        self.assertTrue(linea.error_message)

    def test_a_contact_without_a_phone_is_skipped_not_failed(self):
        """«Omitido» y «fallido» no son lo mismo: uno se reintenta y el
        otro no."""
        campana = self._campana()
        linea = self._destinatario(campana, phone=False)
        with patch('%s.action_send_template' % CANAL) as enviar:
            campana._send_whatsapp_recipient(linea)
        enviar.assert_not_called()
        self.assertEqual(linea.whatsapp_state, 'skipped')

    # ------------------------------------------------------------------
    # El envío
    # ------------------------------------------------------------------

    def test_the_survey_link_goes_in_the_first_variable(self):
        """Si el enlace no va en {{1}}, el cliente recibe la plantilla con
        un hueco vacío y la campaña no mide nada."""
        campana = self._campana()
        linea = self._destinatario(campana)
        recibido = {}

        def capturar(self_canal, nombre, idioma, variables):
            recibido['nombre'] = nombre
            recibido['idioma'] = idioma
            recibido['variables'] = variables

        with patch('%s.action_send_template' % CANAL, autospec=True,
                   side_effect=capturar):
            campana._send_whatsapp_recipient(linea)
        self.assertEqual(recibido['nombre'], 'nps_qa')
        self.assertEqual(recibido['idioma'], 'es')
        self.assertEqual(recibido['variables'][0],
                         'https://ejemplo.invalid/encuesta/1')

    def test_a_sent_recipient_is_marked_with_its_date(self):
        campana = self._campana()
        linea = self._destinatario(campana)
        with patch('%s.action_send_template' % CANAL):
            campana._send_whatsapp_recipient(linea)
        self.assertEqual(linea.whatsapp_state, 'sent')
        self.assertTrue(linea.sent_date)
        self.assertFalse(linea.error_message)

    # ------------------------------------------------------------------
    # Un fallo no puede llevarse la campaña por delante
    # ------------------------------------------------------------------

    def test_one_bad_recipient_does_not_stop_the_rest(self):
        """El fallo que estaba abierto.

        El bucle atrapaba la excepción, pero sin savepoint: si el fallo
        venía de una consulta, PostgreSQL dejaba la transacción abortada
        y reventaban tanto el registro del error como todos los
        destinatarios siguientes. Justo lo que el `except` pretendía
        evitar.
        """
        campana = self._campana(batch_size=10)
        malo = self._destinatario(campana)
        bueno = self._destinatario(campana)
        llamadas = []

        def fallar_el_primero(self_canal, nombre, idioma, variables):
            llamadas.append(variables[0])
            if len(llamadas) == 1:
                # Un fallo de base de datos, no un error de red: es el
                # que dejaba la transacción inservible.
                self_canal.env.cr.execute('SELECT columna_que_no_existe')

        with patch('%s.action_send_template' % CANAL, autospec=True,
                   side_effect=fallar_el_primero):
            campana._process_batch()

        self.assertEqual(len(llamadas), 2,
                         'El segundo destinatario tiene que intentarse igual.')
        self.assertEqual(malo.whatsapp_state, 'failed')
        self.assertTrue(malo.error_message)
        self.assertEqual(bueno.whatsapp_state, 'sent',
                         'El destinatario bueno debe quedar enviado.')

    def test_a_whatsapp_failure_does_not_undo_a_sent_email(self):
        """El savepoint es por canal, no por destinatario: si envolviera
        los dos juntos, un fallo de WhatsApp desharía el correo que ya
        había salido y el destinatario saldría fallido en ambos."""
        campana = self._campana(channel='both', email_subject='NPS QA',
                                email_body='Hola')
        linea = self._destinatario(campana)

        def correo_bien(self_campana, line):
            line.write({'email_state': 'sent'})

        ruta_correo = ('odoo.addons.crm_customer_experience.models.nps_campaign'
                       '.CrmNpsCampaign._send_email_recipient')
        with patch(ruta_correo, autospec=True, side_effect=correo_bien), \
                patch('%s.action_send_template' % CANAL,
                      side_effect=ValueError('Meta rechazó la plantilla')):
            campana._process_batch()

        self.assertEqual(linea.email_state, 'sent',
                         'El correo enviado no puede deshacerse.')
        self.assertEqual(linea.whatsapp_state, 'failed')

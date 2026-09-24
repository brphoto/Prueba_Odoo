from unittest.mock import patch

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestCarrerasWebhook(TransactionCase):
    """Dos mensajes del mismo contacto nuevo, a la vez.

    Meta entrega en paralelo y cada webhook corre en su propia
    transacción. Los dos buscan el canal, ninguno lo encuentra, y los
    dos intentan crearlo. El que pierde se estrellaba con un
    `IntegrityError` sin capturar: la petición entera fallaba, Meta
    reintentaba y el mensaje llegaba tarde. Y como el contacto no tiene
    restricción única, además quedaban dos `res.partner` para el mismo
    número.
    """

    def _crear(self, external_id='593999123456', nombre='Cliente QA'):
        return self.env['chatroom.channel']._find_or_create_from_webhook(
            'whatsapp', external_id, profile_name=nombre)

    def test_the_first_message_creates_channel_and_contact(self):
        canal = self._crear()
        self.assertTrue(canal)
        self.assertEqual(canal.external_id, '593999123456')
        self.assertEqual(canal.partner_id.whatsapp_id, '593999123456')

    def test_a_second_message_reuses_the_same_channel(self):
        primero = self._crear()
        segundo = self._crear()
        self.assertEqual(primero, segundo,
                         'Un contacto tiene una sola conversación.')

    def test_losing_the_race_returns_the_winners_channel(self):
        """Se simula la carrera: el `create` del canal falla como si otro
        worker se hubiera adelantado, y el contacto ya está creado."""
        ganador = self._crear()
        Canal = type(self.env['chatroom.channel'])
        original = Canal.create
        llamadas = []

        def create_que_pierde(self_canal, vals):
            llamadas.append(vals)
            if len(llamadas) == 1:
                # Mismo error que levanta la restricción única.
                self_canal.env.cr.execute(
                    "INSERT INTO chatroom_channel (external_id, channel_type,"
                    " company_id) VALUES (%s, 'whatsapp', %s)",
                    (ganador.external_id, self_canal.env.company.id))
            return original(self_canal, vals)

        with patch.object(Canal, 'create', create_que_pierde):
            resultado = self.env['chatroom.channel']._find_or_create_from_webhook(
                'whatsapp', ganador.external_id, profile_name='Cliente QA')

        self.assertEqual(resultado, ganador,
                         'El perdedor debe quedarse con el canal del ganador.')

    def test_the_loser_does_not_leave_a_duplicate_contact(self):
        """El savepoint envuelve contacto Y canal, así que al perder la
        carrera se deshace todo lo que había creado."""
        ganador = self._crear(external_id='593999777888')
        antes = self.env['res.partner'].search_count(
            [('whatsapp_id', '=', '593999777888')])
        self.assertEqual(antes, 1)

        Canal = type(self.env['chatroom.channel'])
        original = Canal.create
        primera = []

        def create_que_pierde(self_canal, vals):
            if not primera:
                primera.append(1)
                self_canal.env.cr.execute(
                    "INSERT INTO chatroom_channel (external_id, channel_type,"
                    " company_id) VALUES (%s, 'whatsapp', %s)",
                    ('593999777888', self_canal.env.company.id))
            return original(self_canal, vals)

        # Se borra el contacto para forzar que el perdedor intente crearlo.
        self.env['res.partner'].search(
            [('whatsapp_id', '=', '593999777888')]).whatsapp_id = False
        with patch.object(Canal, 'create', create_que_pierde):
            self.env['chatroom.channel']._find_or_create_from_webhook(
                'whatsapp', '593999777888', profile_name='Cliente QA')

        self.assertLessEqual(
            self.env['res.partner'].search_count(
                [('whatsapp_id', '=', '593999777888')]),
            1, 'No puede quedar un contacto duplicado para el mismo número.')

    def test_an_unrelated_integrity_error_is_not_swallowed(self):
        """Solo se absorbe la carrera. Cualquier otro fallo de integridad
        tiene que seguir saliendo: taparlo escondería un bug."""
        from psycopg2 import errors as pg_errors
        Canal = type(self.env['chatroom.channel'])

        def create_que_falla(self_canal, vals):
            raise pg_errors.UniqueViolation('otra restricción distinta')

        with patch.object(Canal, 'create', create_que_falla):
            with self.assertRaises(pg_errors.UniqueViolation):
                self.env['chatroom.channel']._find_or_create_from_webhook(
                    'whatsapp', '593999000555', profile_name='Cliente QA')

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestChatroomUi(TransactionCase):
    """Capa visual del chatroom.

    Son 670 líneas que deciden cómo se ve toda la aplicación y no tenían
    ningún test. Lo que se cubre es el contrato con el navegador: que
    `get_ui_settings` devuelva cada clave que el cliente usa, y que las
    validaciones no dejen entrar valores que romperían la maquetación.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company

    # ------------------------------------------------------------------
    # Contrato con el cliente web
    # ------------------------------------------------------------------

    def test_settings_include_every_key_the_client_reads(self):
        """Si falta una clave, el cliente la lee como `undefined` y aplica
        un valor por defecto en silencio. Así se perdió la densidad de
        mensajes: el SCSS tenía reglas para «compacta» y «espaciosa» pero
        el modelo nunca devolvía `message_density`.
        """
        settings = self.env['chatroom.channel'].get_ui_settings()
        esperadas = {
            'primary_color', 'secondary_color', 'accent_color',
            'background_image', 'sidebar_width', 'icon_scale', 'font_scale',
            'shadow_level', 'logo_url', 'mobile_compact', 'bubble_radius',
            'message_gap', 'bubble_padding', 'message_density',
        }
        self.assertEqual(
            esperadas - set(settings), set(),
            'Faltan claves que el cliente web espera recibir.')

    def test_message_density_reaches_the_client(self):
        """Las tres densidades tienen que llegar tal cual al navegador."""
        for density, gap in (('compact', '4px'),
                             ('comfortable', '8px'),
                             ('spacious', '12px')):
            self.company.chatroom_ui_message_density = density
            settings = self.env['chatroom.channel'].get_ui_settings()
            self.assertEqual(settings['message_density'], density)
            self.assertEqual(settings['message_gap'], gap)

    def test_user_preferences_win_over_the_company(self):
        """El ancho y el tamaño de texto son preferencia de cada agente."""
        self.company.chatroom_ui_sidebar_width = 360
        self.company.chatroom_ui_font_scale = 1.0
        self.env.user.chatroom_ui_user_sidebar_width = 420
        self.env.user.chatroom_ui_user_font_scale = 1.1
        settings = self.env['chatroom.channel'].get_ui_settings()
        self.assertEqual(settings['sidebar_width'], 420)
        self.assertAlmostEqual(settings['font_scale'], 1.1, places=2)

    def test_company_values_apply_when_the_user_has_no_preference(self):
        self.company.chatroom_ui_sidebar_width = 380
        self.env.user.chatroom_ui_user_sidebar_width = 0
        self.assertEqual(
            self.env['chatroom.channel'].get_ui_settings()['sidebar_width'], 380)

    def test_logo_falls_back_to_the_company_logo(self):
        """Sin logo propio de chatroom se usa el de la compañía, no un
        hueco vacío en la cabecera."""
        self.company.chatroom_ui_brand_logo = False
        settings = self.env['chatroom.channel'].get_ui_settings()
        if self.company.logo:
            self.assertIn('res.company', settings['logo_url'] or '')

    # ------------------------------------------------------------------
    # Validaciones que protegen la maquetación
    # ------------------------------------------------------------------

    def test_colors_must_be_hexadecimal(self):
        """Un color inválido llegaría al CSS como basura y dejaría la
        interfaz sin tema."""
        for valor in ('rojo', '#ABC', '#12345G', '', 'rgb(1,2,3)'):
            with self.assertRaises(ValidationError, msg='Se aceptó %r' % valor):
                self.company.chatroom_ui_primary_color = valor

    def test_valid_color_is_accepted(self):
        self.company.chatroom_ui_primary_color = '#0A1B2C'
        self.assertEqual(self.company.chatroom_ui_primary_color, '#0A1B2C')

    def test_sidebar_width_stays_inside_usable_bounds(self):
        for valor in (100, 279, 521, 2000):
            with self.assertRaises(ValidationError, msg='Se aceptó %s px' % valor):
                self.company.chatroom_ui_sidebar_width = valor
        self.company.chatroom_ui_sidebar_width = 400
        self.assertEqual(self.company.chatroom_ui_sidebar_width, 400)

    def test_scales_stay_inside_usable_bounds(self):
        for valor in (0.5, 2.0):
            with self.assertRaises(ValidationError):
                self.company.chatroom_ui_icon_scale = valor
        for valor in (0.5, 1.5):
            with self.assertRaises(ValidationError):
                self.company.chatroom_ui_font_scale = valor

    def test_bubble_radius_stays_inside_usable_bounds(self):
        for valor in (0, 3, 29, 100):
            with self.assertRaises(ValidationError):
                self.company.chatroom_ui_bubble_radius = valor
        self.company.chatroom_ui_bubble_radius = 14
        self.assertEqual(self.company.chatroom_ui_bubble_radius, 14)

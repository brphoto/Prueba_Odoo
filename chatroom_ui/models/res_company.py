import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


HEX_COLOR_RE = re.compile(r'^#[0-9a-fA-F]{6}$')


class ResCompany(models.Model):
    _inherit = 'res.company'

    chatroom_ui_theme_preset = fields.Selection(
        selection=[
            ('professional', 'Profesional'),
            ('ocean', 'Océano'),
            ('whatsapp', 'WhatsApp'),
            ('executive', 'Ejecutivo oscuro'),
            ('custom', 'Personalizado'),
        ], string='Tema de Chatroom', default='professional', required=True,
        help='Usa un tema listo para aplicar o selecciona Personalizado para controlar cada valor manualmente.',
    )
    chatroom_ui_primary_color = fields.Char(
        string='Color principal de Chatroom', default='#714B67', required=True,
    )
    chatroom_ui_secondary_color = fields.Char(
        string='Color secundario de Chatroom', default='#4F3449', required=True,
    )
    chatroom_ui_accent_color = fields.Char(
        string='Color de acento de Chatroom', default='#00A884', required=True,
    )
    chatroom_ui_background_image = fields.Image(
        string='Imagen de fondo del chat', max_width=1600, max_height=900,
        help='Imagen opcional para el fondo del área de mensajes. Se recomienda una textura suave o una marca de agua.',
    )
    chatroom_ui_brand_logo = fields.Image(
        string='Logo de marca de Chatroom', max_width=800, max_height=800,
        help='Logo opcional para la cabecera de Chatroom. Si queda vacío se usa el logo de la compañía.',
    )
    chatroom_ui_sidebar_width = fields.Integer(
        string='Ancho de la bandeja (px)', default=360,
        help='Ancho de la lista de conversaciones en escritorio.',
    )
    chatroom_ui_icon_scale = fields.Float(
        string='Escala de iconos', default=1.0,
        help='1.0 es el tamaño normal. Usa valores entre 0.8 y 1.3.',
    )
    chatroom_ui_font_scale = fields.Float(string='Escala de texto', default=1.0)
    chatroom_ui_shadow_level = fields.Selection(
        [('low', 'Sutil'), ('medium', 'Equilibrada'), ('high', 'Destacada')],
        string='Nivel de sombras', default='medium', required=True,
    )
    chatroom_ui_bubble_radius = fields.Integer(
        string='Redondeado de mensajes (px)', default=14,
    )
    chatroom_ui_message_density = fields.Selection(
        selection=[
            ('compact', 'Compacta'),
            ('comfortable', 'Cómoda'),
            ('spacious', 'Espaciosa'),
        ], string='Densidad de mensajes', default='comfortable', required=True,
    )

    @api.constrains(
        'chatroom_ui_primary_color',
        'chatroom_ui_secondary_color',
        'chatroom_ui_accent_color',
    )
    def _check_chatroom_ui_colors(self):
        for company in self:
            for field_name in (
                'chatroom_ui_primary_color',
                'chatroom_ui_secondary_color',
                'chatroom_ui_accent_color',
            ):
                value = getattr(company, field_name)
                if not HEX_COLOR_RE.fullmatch(value or ''):
                    raise ValidationError(_(
                        'El campo %s debe contener un color hexadecimal válido, por ejemplo #714B67.',
                        company._fields[field_name].string,
                    ))

    @api.constrains('chatroom_ui_sidebar_width')
    def _check_chatroom_ui_sidebar_width(self):
        for company in self:
            if not 280 <= company.chatroom_ui_sidebar_width <= 520:
                raise ValidationError(_('El ancho de la bandeja debe estar entre 280 y 520 px.'))

    @api.constrains('chatroom_ui_icon_scale')
    def _check_chatroom_ui_icon_scale(self):
        for company in self:
            if not 0.8 <= company.chatroom_ui_icon_scale <= 1.3:
                raise ValidationError(_('La escala de iconos debe estar entre 0.8 y 1.3.'))

    @api.constrains('chatroom_ui_font_scale')
    def _check_chatroom_ui_font_scale(self):
        for company in self:
            if not 0.85 <= company.chatroom_ui_font_scale <= 1.2:
                raise ValidationError(_('La escala de texto debe estar entre 0.85 y 1.2.'))

    @api.constrains('chatroom_ui_bubble_radius')
    def _check_chatroom_ui_bubble_radius(self):
        for company in self:
            if not 4 <= company.chatroom_ui_bubble_radius <= 28:
                raise ValidationError(_('El redondeado de mensajes debe estar entre 4 y 28 px.'))

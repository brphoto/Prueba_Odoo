from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    chatroom_ui_user_sidebar_width = fields.Integer(
        string='Bandeja de Chatroom (px)', default=0,
        help='Sobrescribe el ancho de la bandeja solo para este usuario. 0 usa el valor de la compañía.',
    )
    chatroom_ui_user_font_scale = fields.Float(
        string='Texto de Chatroom', default=0.0,
        help='Sobrescribe el tamaño del texto solo para este usuario. 0 usa el valor de la compañía.',
    )
    chatroom_ui_mobile_compact = fields.Boolean(
        string='Modo compacto en móvil',
        help='Reduce la altura de la barra y prioriza la conversación en pantallas pequeñas.',
    )

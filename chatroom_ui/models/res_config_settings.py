from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    chatroom_ui_primary_color = fields.Char(
        related='company_id.chatroom_ui_primary_color', readonly=False,
    )
    chatroom_ui_secondary_color = fields.Char(
        related='company_id.chatroom_ui_secondary_color', readonly=False,
    )
    chatroom_ui_accent_color = fields.Char(
        related='company_id.chatroom_ui_accent_color', readonly=False,
    )
    chatroom_ui_background_image = fields.Image(
        related='company_id.chatroom_ui_background_image', readonly=False,
    )
    chatroom_ui_sidebar_width = fields.Integer(
        related='company_id.chatroom_ui_sidebar_width', readonly=False,
    )
    chatroom_ui_icon_scale = fields.Float(
        related='company_id.chatroom_ui_icon_scale', readonly=False,
    )
    chatroom_ui_bubble_radius = fields.Integer(
        related='company_id.chatroom_ui_bubble_radius', readonly=False,
    )
    chatroom_ui_message_density = fields.Selection(
        related='company_id.chatroom_ui_message_density', readonly=False,
    )

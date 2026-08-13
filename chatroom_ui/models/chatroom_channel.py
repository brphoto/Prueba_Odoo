from odoo import api, models


class ChatroomChannel(models.Model):
    _inherit = 'chatroom.channel'

    @api.model
    def get_ui_settings(self):
        """Return the current company's safe visual settings to the web client."""
        company = self.env.company
        user = self.env.user
        density_values = {
            'compact': {'gap': '4px', 'padding': '7px 10px'},
            'comfortable': {'gap': '8px', 'padding': '9px 12px'},
            'spacious': {'gap': '12px', 'padding': '12px 14px'},
        }
        density = density_values.get(company.chatroom_ui_message_density, density_values['comfortable'])
        return {
            'primary_color': company.chatroom_ui_primary_color,
            'secondary_color': company.chatroom_ui_secondary_color,
            'accent_color': company.chatroom_ui_accent_color,
            'background_image': (
                '/web/image/res.company/%s/chatroom_ui_background_image' % company.id
                if company.chatroom_ui_background_image else False
            ),
            'sidebar_width': user.chatroom_ui_user_sidebar_width or company.chatroom_ui_sidebar_width,
            'icon_scale': company.chatroom_ui_icon_scale,
            'font_scale': user.chatroom_ui_user_font_scale or company.chatroom_ui_font_scale,
            'shadow_level': company.chatroom_ui_shadow_level,
            'logo_url': (
                '/web/image/res.company/%s/chatroom_ui_brand_logo' % company.id
                if company.chatroom_ui_brand_logo else
                '/web/image/res.company/%s/logo' % company.id if company.logo else False
            ),
            'mobile_compact': user.chatroom_ui_mobile_compact,
            'bubble_radius': company.chatroom_ui_bubble_radius,
            'message_gap': density['gap'],
            'bubble_padding': density['padding'],
        }

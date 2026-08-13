from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    chatroom_ui_theme_preset = fields.Selection(
        related='company_id.chatroom_ui_theme_preset', readonly=False,
    )
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
    chatroom_ui_brand_logo = fields.Image(
        related='company_id.chatroom_ui_brand_logo', readonly=False,
    )
    chatroom_ui_sidebar_width = fields.Integer(
        related='company_id.chatroom_ui_sidebar_width', readonly=False,
    )
    chatroom_ui_icon_scale = fields.Float(
        related='company_id.chatroom_ui_icon_scale', readonly=False,
    )
    chatroom_ui_font_scale = fields.Float(
        related='company_id.chatroom_ui_font_scale', readonly=False,
    )
    chatroom_ui_shadow_level = fields.Selection(
        related='company_id.chatroom_ui_shadow_level', readonly=False,
    )
    chatroom_ui_bubble_radius = fields.Integer(
        related='company_id.chatroom_ui_bubble_radius', readonly=False,
    )
    chatroom_ui_message_density = fields.Selection(
        related='company_id.chatroom_ui_message_density', readonly=False,
    )

    def action_reset_chatroom_ui_defaults(self):
        self.ensure_one()
        self.update({
            'chatroom_ui_theme_preset': 'professional',
            'chatroom_ui_primary_color': '#714B67',
            'chatroom_ui_secondary_color': '#4F3449',
            'chatroom_ui_accent_color': '#00A884',
            'chatroom_ui_sidebar_width': 360,
            'chatroom_ui_icon_scale': 1.0,
            'chatroom_ui_font_scale': 1.0,
            'chatroom_ui_shadow_level': 'medium',
            'chatroom_ui_bubble_radius': 14,
            'chatroom_ui_message_density': 'comfortable',
        })
        return True

    @api.onchange('chatroom_ui_theme_preset')
    def _onchange_chatroom_ui_theme_preset(self):
        presets = {
            'professional': {
                'primary': '#714B67', 'secondary': '#4F3449', 'accent': '#00A884',
                'sidebar': 360, 'icons': 1.0, 'font': 1.0, 'shadow': 'medium', 'radius': 14, 'density': 'comfortable',
            },
            'ocean': {
                'primary': '#0F766E', 'secondary': '#155E75', 'accent': '#06B6D4',
                'sidebar': 380, 'icons': 1.0, 'font': 1.0, 'shadow': 'medium', 'radius': 16, 'density': 'comfortable',
            },
            'whatsapp': {
                'primary': '#128C7E', 'secondary': '#075E54', 'accent': '#25D366',
                'sidebar': 360, 'icons': 1.05, 'font': 1.0, 'shadow': 'low', 'radius': 12, 'density': 'compact',
            },
            'executive': {
                'primary': '#1E293B', 'secondary': '#0F172A', 'accent': '#F59E0B',
                'sidebar': 370, 'icons': 0.95, 'font': 0.98, 'shadow': 'high', 'radius': 10, 'density': 'spacious',
            },
        }
        values = presets.get(self.chatroom_ui_theme_preset)
        if not values:
            return
        self.update({
            'chatroom_ui_primary_color': values['primary'],
            'chatroom_ui_secondary_color': values['secondary'],
            'chatroom_ui_accent_color': values['accent'],
            'chatroom_ui_sidebar_width': values['sidebar'],
            'chatroom_ui_icon_scale': values['icons'],
            'chatroom_ui_bubble_radius': values['radius'],
            'chatroom_ui_font_scale': values.get('font', 1.0),
            'chatroom_ui_shadow_level': values.get('shadow', 'medium'),
            'chatroom_ui_message_density': values['density'],
        })

    @api.onchange(
        'chatroom_ui_primary_color',
        'chatroom_ui_secondary_color',
        'chatroom_ui_accent_color',
        'chatroom_ui_sidebar_width',
        'chatroom_ui_icon_scale',
        'chatroom_ui_font_scale',
        'chatroom_ui_shadow_level',
        'chatroom_ui_bubble_radius',
        'chatroom_ui_message_density',
    )
    def _onchange_chatroom_ui_custom_values(self):
        if self.chatroom_ui_theme_preset and not self._theme_values_match_preset():
            self.chatroom_ui_theme_preset = 'custom'

    def _theme_values_match_preset(self):
        presets = {
            'professional': ('#714B67', '#4F3449', '#00A884', 360, 1.0, 1.0, 'medium', 14, 'comfortable'),
            'ocean': ('#0F766E', '#155E75', '#06B6D4', 380, 1.0, 1.0, 'medium', 16, 'comfortable'),
            'whatsapp': ('#128C7E', '#075E54', '#25D366', 360, 1.05, 1.0, 'low', 12, 'compact'),
            'executive': ('#1E293B', '#0F172A', '#F59E0B', 370, 0.95, 0.98, 'high', 10, 'spacious'),
        }
        expected = presets.get(self.chatroom_ui_theme_preset)
        if not expected:
            return False
        current = (
            self.chatroom_ui_primary_color,
            self.chatroom_ui_secondary_color,
            self.chatroom_ui_accent_color,
            self.chatroom_ui_sidebar_width,
            self.chatroom_ui_icon_scale,
            self.chatroom_ui_font_scale,
            self.chatroom_ui_shadow_level,
            self.chatroom_ui_bubble_radius,
            self.chatroom_ui_message_density,
        )
        return current == expected

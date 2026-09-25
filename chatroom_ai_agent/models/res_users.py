# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError

PANEL_PREFS = [
    ('auto', 'Compacto (se abre si hay algo por aprobar)'),
    ('open', 'Siempre abierto'),
    ('hidden', 'Oculto'),
]


class ResUsers(models.Model):
    _inherit = 'res.users'

    chatroom_ai_agent_panel = fields.Selection(
        PANEL_PREFS, string='Panel del Agente IA en el chat', default='auto',
        help='Cómo se muestra el panel del Agente IA junto a cada conversación.')

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + ['chatroom_ai_agent_panel']

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + ['chatroom_ai_agent_panel']

    @api.model
    def set_chatroom_ai_agent_panel(self, pref):
        """Guarda la preferencia del usuario actual desde el propio panel."""
        if pref not in dict(PANEL_PREFS):
            raise UserError('Preferencia de panel no válida.')
        self.env.user.sudo().chatroom_ai_agent_panel = pref
        return pref

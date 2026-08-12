# -*- coding: utf-8 -*-
from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    chatroom_color = fields.Char(
        string="Color del asesor", default="#3b82f6",
        help="Color hexadecimal usado en los badges y en la trazabilidad de mensajes del Chatroom.",
    )

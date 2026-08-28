# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    chatroom_color = fields.Char(
        string="Color del asesor", default="#3b82f6",
        help="Color hexadecimal usado en los badges y en la trazabilidad de mensajes del Chatroom.",
    )

    # Compatibilidad con vistas/dominios que pudieron quedar de la antigua
    # integración Acrux/whatsapp_connector en una base restaurada. El módulo
    # activo es chatroom_whatsapp y sus grupos son la fuente de verdad actual.
    # Mantener este campo evita que una vista heredada deje de abrirse mientras
    # se termina la limpieza de módulos antiguos de la base.
    is_chatroom_group = fields.Boolean(
        string="Usuario de ChatRoom",
        compute="_compute_is_chatroom_group",
        compute_sudo=True,
        store=True,
    )

    @api.depends("group_ids", "share")
    def _compute_is_chatroom_group(self):
        group_xmlids = (
            "chatroom_whatsapp.group_chatroom_user",
            "chatroom_whatsapp.group_chatroom_supervisor",
            "chatroom_whatsapp.group_chatroom_manager",
        )
        groups = self.env["res.groups"].browse()
        for xmlid in group_xmlids:
            group = self.env.ref(xmlid, raise_if_not_found=False)
            if group:
                groups |= group
        chatroom_user_ids = set(groups.mapped("user_ids").ids)
        for user in self:
            user.is_chatroom_group = not user.share and user.id in chatroom_user_ids

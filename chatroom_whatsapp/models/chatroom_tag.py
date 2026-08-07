# -*- coding: utf-8 -*-
from odoo import fields, models


class ChatroomTag(models.Model):
    """Etiqueta libre para categorizar conversaciones (ej. 'Reclamo',
    'Venta caliente'), pensada para poder filtrar y agrupar en reportes
    -no solo para verlas en el chat-, así que vive como modelo propio en
    vez de un simple Selection."""
    _name = 'chatroom.tag'
    _description = "Etiqueta de Chatroom"
    _order = 'name'

    name = fields.Char(required=True)
    color = fields.Integer(string="Color")

    _name_uniq = models.Constraint(
        'unique(name)',
        "Ya existe una etiqueta con ese nombre.",
    )

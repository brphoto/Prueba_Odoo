# -*- coding: utf-8 -*-
from odoo import fields, models


class ChatroomCannedResponse(models.Model):
    """Respuesta guardada que un agente puede insertar con un clic en el
    composer del chat, para preguntas frecuentes sin depender de la IA."""
    _name = 'chatroom.canned.response'
    _description = "Respuesta rápida de Chatroom"
    _order = 'name'

    name = fields.Char(string="Título", required=True, help="Solo para identificarla en la lista.")
    message = fields.Text(string="Mensaje", required=True)

    _name_uniq = models.Constraint(
        'unique(name)',
        "Ya existe una respuesta rápida con ese título.",
    )

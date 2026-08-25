# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ChatroomMessage(models.Model):
    _inherit = 'chatroom.message'

    ai_generated = fields.Boolean(
        string='Generado por IA', default=False, index=True, copy=False,
        readonly=True,
        help='Identifica mensajes salientes enviados por una automatizacion IA. No se puede marcar a mano desde la interfaz.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.context.get('chatroom_ai_generated'):
            vals_list = [dict(vals, ai_generated=True)
                         if vals.get('direction') == 'outbound' else vals
                         for vals in vals_list]
        return super().create(vals_list)

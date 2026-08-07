# -*- coding: utf-8 -*-
from odoo import fields, models


class ChatroomReassignWizard(models.TransientModel):
    _name = 'chatroom.reassign.wizard'
    _description = "Reasignar conversaciones de Chatroom"

    assigned_user_id = fields.Many2one(
        'res.users', string="Nuevo agente", required=True,
        help="Se aplica a todas las conversaciones seleccionadas en la lista.")

    def action_confirm(self):
        self.ensure_one()
        channel_ids = self.env.context.get('active_ids', [])
        self.env['chatroom.channel'].browse(channel_ids).write({
            'assigned_user_id': self.assigned_user_id.id,
        })
        return {'type': 'ir.actions.act_window_close'}

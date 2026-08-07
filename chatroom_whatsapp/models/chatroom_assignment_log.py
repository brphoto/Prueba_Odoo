# -*- coding: utf-8 -*-
from odoo import fields, models


class ChatroomAssignmentLog(models.Model):
    _name = 'chatroom.assignment.log'
    _description = "Historial de asignación de Chatroom"
    _order = 'changed_at desc, id desc'

    channel_id = fields.Many2one(
        'chatroom.channel', string="Conversación", required=True,
        ondelete='cascade', index=True)
    previous_user_id = fields.Many2one('res.users', string="Agente anterior")
    new_user_id = fields.Many2one('res.users', string="Agente nuevo")
    reason = fields.Selection(
        [('manual', "Reasignación manual"),
         ('sla', "Liberación por SLA"),
         ('auto', "Asignación automática"),
         ('system', "Sistema")],
        default='manual', required=True)
    note = fields.Char(string="Detalle")
    changed_by = fields.Many2one(
        'res.users', string="Cambió el responsable",
        default=lambda self: self.env.user, required=True)
    changed_at = fields.Datetime(
        string="Fecha y hora", default=fields.Datetime.now, required=True,
        index=True)

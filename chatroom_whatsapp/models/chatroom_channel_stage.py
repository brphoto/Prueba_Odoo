# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ChatroomChannelStage(models.Model):
    _name = 'chatroom.channel.stage'
    _description = 'Etapa de conversación de Chatroom'
    _order = 'sequence, id'

    name = fields.Char(string='Nombre', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    fold = fields.Boolean(
        string='Plegada en kanban',
        help='Oculta las tarjetas de esta etapa en la vista kanban.')
    color = fields.Integer(string='Color', default=0)
    technical_state = fields.Selection(
        [('open', 'Abierta'), ('pending', 'Pendiente'), ('closed', 'Cerrada')],
        string='Estado operativo', required=True, default='open',
        help='Estado técnico usado por las automatizaciones y los filtros heredados.')
    is_final = fields.Boolean(
        string='Etapa final',
        help='Marca la conversación como cerrada al moverla aquí.')
    default_for_new = fields.Boolean(
        string='Predeterminada para nuevas conversaciones',
        help='Se usa al crear conversaciones nuevas cuyo estado no viene indicado.')
    description = fields.Text(string='Descripción')

    _name_unique = models.Constraint(
        'unique(name)',
        'Ya existe una etapa con ese nombre.',
    )

    @api.constrains('default_for_new')
    def _check_single_default(self):
        for record in self.filtered('default_for_new'):
            other = self.search([
                ('id', '!=', record.id),
                ('default_for_new', '=', True),
                ('active', '=', True),
            ], limit=1)
            if other:
                raise ValidationError(_(
                    'Solo puede existir una etapa predeterminada para nuevas conversaciones.'))

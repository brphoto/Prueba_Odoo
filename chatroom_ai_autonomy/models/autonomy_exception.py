# -*- coding: utf-8 -*-
from odoo import _, fields, models


class ChatroomAiAutonomyException(models.Model):
    _name = 'chatroom.ai.autonomy.exception'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Excepción operativa del agente IA'
    _order = 'severity desc, create_date desc, id desc'

    name = fields.Char(string='Excepción', required=True)
    task_id = fields.Many2one('chatroom.ai.task', string='Tarea', ondelete='cascade', index=True)
    channel_id = fields.Many2one('chatroom.channel', string='Conversación', ondelete='set null', index=True)
    partner_id = fields.Many2one('res.partner', string='Cliente', ondelete='set null', index=True)
    policy_id = fields.Many2one('chatroom.ai.autonomy.policy', string='Política')
    exception_type = fields.Selection([
        ('approval', 'Aprobación humana'),
        ('blocked', 'Acción bloqueada'),
        ('verification', 'Resultado no verificado'),
        ('error', 'Error de ejecución'),
    ], string='Tipo', required=True, default='approval')
    severity = fields.Selection([
        ('low', 'Baja'), ('medium', 'Media'), ('high', 'Alta'),
    ], string='Severidad', required=True, default='medium')
    state = fields.Selection([
        ('open', 'Abierta'), ('in_progress', 'En revisión'),
        ('resolved', 'Resuelta'), ('ignored', 'Ignorada'),
    ], string='Estado', required=True, default='open', index=True)
    reason = fields.Text(string='Motivo', required=True)
    recommended_action = fields.Text(string='Acción recomendada')
    user_id = fields.Many2one('res.users', string='Responsable', default=lambda self: self.env.user)
    resolved_at = fields.Datetime(string='Resuelta el', readonly=True)

    def action_start(self):
        self.write({'state': 'in_progress'})
        return True

    def action_resolve(self):
        self.write({'state': 'resolved', 'resolved_at': fields.Datetime.now()})
        return True

    def action_ignore(self):
        self.write({'state': 'ignored', 'resolved_at': fields.Datetime.now()})
        return True

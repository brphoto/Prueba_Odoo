# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ChatroomOperationsPlaybookRun(models.Model):
    """Persistent execution ledger for communication playbooks.

    The playbook itself keeps a quick last-result summary. This model keeps
    the complete operational trail without storing customer message content
    or secrets, so supervisors can audit automatic runs safely.
    """

    _name = 'chatroom.operations.playbook.run'
    _description = 'Ejecución de playbook de comunicación'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'execution_date desc, id desc'

    name = fields.Char(string='Ejecución', compute='_compute_name', store=True)
    playbook_id = fields.Many2one(
        'chatroom.operations.playbook', string='Playbook', required=True,
        ondelete='cascade', index=True)
    company_id = fields.Many2one('res.company', string='Empresa', required=True, index=True)
    execution_date = fields.Datetime(
        string='Ejecutada el', required=True, default=fields.Datetime.now, index=True)
    execution_type = fields.Selection([
        ('manual', 'Manual'), ('cron', 'Automática'),
    ], string='Origen', required=True, default='manual')
    state = fields.Selection([
        ('done', 'Completada'), ('partial', 'Con incidencias'), ('error', 'Fallida'),
    ], string='Estado', required=True, default='done')
    channels_processed = fields.Integer(string='Canales procesados')
    notified_count = fields.Integer(string='Avisos internos')
    sent_count = fields.Integer(string='Plantillas enviadas')
    blocked_count = fields.Integer(string='Bloqueados')
    error_count = fields.Integer(string='Errores')
    summary = fields.Char(string='Resumen')

    @api.depends('playbook_id', 'execution_date')
    def _compute_name(self):
        for run in self:
            date = fields.Datetime.to_string(run.execution_date) if run.execution_date else ''
            run.name = '%s — %s' % (run.playbook_id.display_name, date)

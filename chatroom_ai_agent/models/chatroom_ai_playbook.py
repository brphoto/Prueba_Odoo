# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ChatroomAiPlaybook(models.Model):
    _name = 'chatroom.ai.playbook'
    _description = 'Acción reutilizable del agente IA'
    _order = 'sequence, name'

    name = fields.Char(string='Nombre de la acción', required=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    category = fields.Selection([
        ('service', 'Atención y servicio'),
        ('commercial', 'Ventas y oportunidades'),
        ('collection', 'Cobranza y pagos'),
        ('retention', 'Seguimiento y reactivación'),
        ('analysis', 'Análisis y clasificación'),
        ('custom', 'Personalizada'),
    ], string='Categoría', required=True, default='service')
    task_type = fields.Selection([
        ('orchestrate', 'Analizar conversación completa'),
        ('classify_customer', 'Clasificar cliente RFM/ABC'),
        ('qualify_lead', 'Calificar oportunidad'),
        ('prepare_reply', 'Preparar respuesta'),
        ('followup', 'Preparar seguimiento'),
        ('collect_payment', 'Preparar cobranza'),
        ('sales_conversion', 'Convertir conversación en venta'),
        ('daily_review', 'Revisión comercial'),
    ], string='Acción que ejecuta', required=True, default='prepare_reply')
    scope = fields.Selection([
        ('all', 'Todos los chats activos'),
        ('channels', 'Chats seleccionados'),
        ('partners', 'Clientes seleccionados'),
    ], string='Alcance', required=True, default='all')
    channel_ids = fields.Many2many(
        'chatroom.channel', 'chatroom_ai_playbook_channel_rel',
        'playbook_id', 'channel_id', string='Chats seleccionados')
    partner_ids = fields.Many2many(
        'res.partner', 'chatroom_ai_playbook_partner_rel',
        'playbook_id', 'partner_id', string='Clientes seleccionados')
    instruction = fields.Text(
        string='Instrucción para la IA', required=True,
        help='Indica qué debe revisar y qué resultado debe dejar preparado.')
    description = fields.Text(string='Qué hace')
    example_prompt = fields.Text(string='Ejemplo de solicitud')
    approval_required = fields.Boolean(
        string='Requiere aprobación humana', default=True,
        help='Las acciones sensibles seguirán protegidas aunque se desactive esta opción.')
    max_tasks = fields.Integer(string='Máximo de chats por aplicación', default=20)
    max_attempts = fields.Integer(string='Máximo de intentos', default=3)
    is_example = fields.Boolean(string='Ejemplo incluido', readonly=True)
    company_id = fields.Many2one(
        'res.company', string='Empresa', default=lambda self: self.env.company, index=True)
    use_count = fields.Integer(string='Veces aplicada', readonly=True)
    last_run = fields.Datetime(string='Última aplicación', readonly=True)
    last_run_count = fields.Integer(string='Tareas creadas', readonly=True)
    last_run_summary = fields.Char(string='Resultado de la última aplicación', readonly=True)
    last_error = fields.Text(string='Último error', readonly=True)

    @api.constrains('max_tasks', 'max_attempts', 'scope', 'channel_ids', 'partner_ids')
    def _check_configuration(self):
        for playbook in self:
            if playbook.max_tasks <= 0:
                raise ValidationError(_('El máximo de chats debe ser mayor que cero.'))
            if playbook.max_attempts <= 0:
                raise ValidationError(_('El máximo de intentos debe ser mayor que cero.'))
            if playbook.scope == 'channels' and not playbook.channel_ids:
                raise ValidationError(_('Selecciona al menos un chat para este alcance.'))
            if playbook.scope == 'partners' and not playbook.partner_ids:
                raise ValidationError(_('Selecciona al menos un cliente para este alcance.'))

    def _target_channels(self):
        self.ensure_one()
        Channel = self.env['chatroom.channel']
        company = self.company_id or self.env.company
        base_domain = [
            ('company_id', '=', company.id),
            ('state', 'in', ('open', 'pending')),
        ]
        if self.scope == 'channels':
            return self.channel_ids.filtered(
                lambda channel: channel.company_id == company
                and channel.state in ('open', 'pending'))[:self.max_tasks]
        if self.scope == 'partners':
            base_domain.append(('partner_id', 'in', self.partner_ids.ids or [0]))
        return Channel.search(base_domain, order='write_date desc, id desc', limit=self.max_tasks)

    def _create_task_for_channel(self, channel):
        self.ensure_one()
        Task = self.env['chatroom.ai.task']
        duplicate = Task.search([
            ('channel_id', '=', channel.id),
            ('playbook_id', '=', self.id),
            ('state', 'in', ('awaiting_approval', 'planned', 'running')),
        ], limit=1)
        if duplicate:
            return duplicate
        task = Task.create_from_channel(
            channel,
            task_type=self.task_type,
            prompt=self.instruction,
            approval_required=self.approval_required,
            playbook=self,
        )
        task.action_plan()
        if not self.approval_required and task.state == 'planned':
            task.action_run()
        return task

    def action_apply(self):
        """Apply the saved action to its configured scope and show created tasks."""
        self.ensure_one()
        channels = self._target_channels()
        if not channels:
            raise UserError(_('No se encontraron chats activos para este alcance.'))
        created_ids = []
        errors = []
        for channel in channels:
            try:
                task = self._create_task_for_channel(channel)
                if task and task.id not in created_ids:
                    created_ids.append(task.id)
            except Exception as exc:
                errors.append('%s: %s' % (channel.display_name, exc))
        self.sudo().write({
            'use_count': self.use_count + len(created_ids),
            'last_run': fields.Datetime.now(),
            'last_run_count': len(created_ids),
            'last_run_summary': _('%s tarea(s) creadas para %s chat(s).') % (
                len(created_ids), len(channels)),
            'last_error': '\n'.join(errors)[:4000] or False,
        })
        if not created_ids:
            raise UserError(_('No se pudo crear ninguna tarea. Revisa los duplicados o el detalle del error.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Tareas creadas por acción'),
            'res_model': 'chatroom.ai.task',
            'view_mode': 'list,form',
            'domain': [('id', 'in', created_ids)],
            'context': {'search_default_pending': 0},
        }

    def apply_to_channel(self, channel):
        self.ensure_one()
        if not channel or channel._name != 'chatroom.channel':
            raise UserError(_('Debes seleccionar una conversación válida.'))
        if self.company_id and channel.company_id != self.company_id:
            raise UserError(_('La acción y la conversación pertenecen a empresas diferentes.'))
        task = self._create_task_for_channel(channel)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Tarea IA: %s') % self.name,
            'res_model': 'chatroom.ai.task',
            'res_id': task.id,
            'views': [(False, 'form')],
            'target': 'new',
        }

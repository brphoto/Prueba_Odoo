# -*- coding: utf-8 -*-
from odoo import _, models
from odoo.exceptions import UserError


class ChatroomChannel(models.Model):
    _inherit = 'chatroom.channel'

    def _ai_requires_approval(self):
        """El perfil del Agente IA gobierna las respuestas automáticas.

        Las herramientas sensibles siguen teniendo su propia aprobación en
        ``chatroom.ai.tool``. Si el parámetro del agente todavía no existe,
        se conserva el comportamiento seguro del módulo base.
        """
        icp = self.env['ir.config_parameter'].sudo()
        configured = icp.get_param('chatroom_ai_agent.require_approval')
        # get_param() devuelve False cuando no existe el registro. Ese valor
        # no puede interpretarse como una desactivación: el modo seguro por
        # defecto debe exigir revisión humana.
        if configured not in (False, None, ''):
            return str(configured).strip().lower() in ('1', 'true', 'yes', 'on')
        return super()._ai_requires_approval()

    def get_ai_agent_data(self):
        self.ensure_one()
        can_use = self.env.user.has_group('chatroom_ai_agent.group_chatroom_ai_agent_user')
        if not can_use:
            return {'can_use': False, 'task': False}
        task = self.env['chatroom.ai.task'].search([
            ('channel_id', '=', self.id),
            ('state', '!=', 'cancelled'),
        ], order='create_date desc, id desc', limit=1)
        tasks = self.env['chatroom.ai.task'].sudo()
        pending_domain = [('state', 'in', ('awaiting_approval', 'planned', 'running'))]
        icp = self.env['ir.config_parameter'].sudo()
        playbooks = []
        if 'chatroom.ai.playbook' in self.env:
            playbook_model = self.env['chatroom.ai.playbook'].sudo()
            for playbook in playbook_model.search([
                ('active', '=', True),
                '|', ('company_id', '=', False), ('company_id', '=', self.company_id.id),
            ], order='sequence, name', limit=20):
                playbooks.append({
                    'id': playbook.id,
                    'name': playbook.name,
                    'category': playbook.category,
                    'task_type': playbook.task_type,
                    'task_type_label': dict(playbook._fields['task_type'].selection).get(
                        playbook.task_type, playbook.task_type),
                    'description': playbook.description or '',
                    'approval_required': playbook.approval_required,
                })
        return {
            'can_use': True,
            'pending_count': tasks.search_count(pending_domain),
            'approval_count': tasks.search_count([('state', '=', 'awaiting_approval')]),
            'high_risk_count': tasks.search_count([
                ('risk_level', '=', 'high'),
                ('state', 'not in', ('done', 'cancelled')),
            ]),
            'mode': icp.get_param('chatroom_ai_agent.mode', 'supervised'),
            'playbooks': playbooks,
            'task': {
                'id': task.id,
                'name': task.name,
                'state': task.state,
                'state_label': dict(task._fields['state'].selection).get(task.state, task.state),
                'action_count': len(task.action_ids),
                'result_summary': task.result_summary or '',
                'result_preview': task.result_preview or '',
                'risk_level': task.risk_level,
                'approval_required': task.approval_required,
            } if task else False,
        }

    def action_ai_agent_apply_playbook(self, playbook_id):
        self.ensure_one()
        if 'chatroom.ai.playbook' not in self.env:
            raise UserError(_('La biblioteca de acciones no está instalada.'))
        playbook = self.env['chatroom.ai.playbook'].browse(int(playbook_id)).exists()
        if not playbook or not playbook.active:
            raise UserError(_('La acción guardada no está disponible.'))
        return playbook.apply_to_channel(self)

    def action_ai_agent_create_task(self):
        self.ensure_one()
        task = self.env['chatroom.ai.task'].create_from_channel(self)
        task.action_plan()
        return {
            'type': 'ir.actions.act_window', 'name': _('Plan IA'),
            'res_model': 'chatroom.ai.task', 'res_id': task.id,
            'views': [(False, 'form')], 'target': 'new',
        }

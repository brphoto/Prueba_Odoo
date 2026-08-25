# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models


_logger = logging.getLogger(__name__)


class ChatroomMessage(models.Model):
    _inherit = 'chatroom.message'

    @api.model_create_multi
    def create(self, vals_list):
        messages = super().create(vals_list)
        icp = self.env['ir.config_parameter'].sudo()
        enabled = icp.get_param(
            'chatroom_ai_agent.event_orchestration', 'False') == 'True'
        if not enabled or 'chatroom.ai.automation' not in self.env:
            return messages
        automation_model = self.env['chatroom.ai.automation'].sudo()
        automations = automation_model.search([
            ('active', '=', True), ('trigger', '=', 'open_conversation'),
        ], order='sequence, id')
        if not automations:
            return messages
        tasks = self.env['chatroom.ai.task'].sudo()
        for message in messages.filtered(lambda item: item.direction == 'inbound' and item.channel_id):
            channel = message.channel_id
            if channel.ai_paused:
                continue
            for automation in automations[:1]:
                try:
                    # El webhook no debe fallar porque una automatización tenga
                    # un error. La tarea queda auditada cuando puede crearse y
                    # el mensaje sigue disponible para el equipo humano.
                    with self.env.cr.savepoint():
                        duplicate = tasks.search_count([
                            ('channel_id', '=', channel.id),
                            ('automation_id', '=', automation.id),
                            ('state', 'in', ('draft', 'awaiting_approval', 'planned', 'running')),
                        ])
                        if duplicate:
                            continue
                        task = tasks.create_from_channel(
                            channel, automation.task_type or 'followup',
                            automation.instruction or automation.name,
                            automation.approval_required,
                            automation=automation)
                        task.action_plan()

                    # La ejecución automática nunca salta las barreras propias
                    # de las herramientas (envíos, cobros, cotizaciones y
                    # actividades). En modo supervisado solo se deja lista la
                    # tarea para aprobación humana.
                    automatic = (
                        icp.get_param('chatroom_ai_agent.enabled', 'False') == 'True'
                        and icp.get_param('chatroom_ai_agent.mode', 'supervised') == 'automatic'
                        and not automation.approval_required
                        and task.state == 'planned'
                    )
                    if automatic:
                        try:
                            task.action_run()
                        except Exception:  # noqa: BLE001 - no romper la ingesta
                            _logger.exception(
                                'No se pudo ejecutar automáticamente la tarea IA %s para el canal %s',
                                task.id, channel.id)
                except Exception:  # noqa: BLE001 - no romper la ingesta
                    _logger.exception(
                        'No se pudo orquestar el mensaje entrante %s del canal %s',
                        message.id, channel.id)
        return messages

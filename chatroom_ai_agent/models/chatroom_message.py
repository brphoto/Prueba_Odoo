# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models


_logger = logging.getLogger(__name__)


class ChatroomMessage(models.Model):
    _inherit = 'chatroom.message'

    @api.model_create_multi
    def create(self, vals_list):
        messages = super().create(vals_list)
        icp = self.env['ir.config_parameter'].sudo()
        event_enabled = icp.get_param(
            'chatroom_ai_agent.event_orchestration', 'False') == 'True'
        router_enabled = icp.get_param(
            'chatroom_ai_agent.commercial_router_enabled', 'False') == 'True'
        if icp.get_param(
                'chatroom_ai_agent.production_orchestrator', 'False') == 'True':
            # El servicio central reemplaza las dos rutas antiguas para que
            # cada mensaje tenga una sola decisión y una sola clave idempotente.
            self.env['chatroom.ai.orchestrator'].process_inbound(messages)
            return messages
        if not event_enabled and not router_enabled:
            return messages
        automation_model = self.env['chatroom.ai.automation'].sudo() if 'chatroom.ai.automation' in self.env else self.env['chatroom.message']
        automations = automation_model.search([
            ('active', '=', True), ('trigger', '=', 'open_conversation'),
        ], order='sequence, id') if event_enabled and 'chatroom.ai.automation' in self.env else automation_model.browse()
        tasks = self.env['chatroom.ai.task'].sudo()
        # Que canales tienen ya una tarea abierta, y con que automatizacion,
        # resuelto en UNA consulta para todo el lote. Los conjuntos se van
        # alimentando con lo que se crea mas abajo, para que dos mensajes
        # del mismo canal en el mismo lote se comporten como antes.
        inbound = messages.filtered(
            lambda item: item.direction == 'inbound' and item.channel_id)
        busy_channels = set()
        busy_pairs = set()
        if inbound:
            for task in tasks.search([
                ('channel_id', 'in', inbound.channel_id.ids),
                ('state', 'in', ('draft', 'awaiting_approval', 'planned', 'running')),
            ]):
                busy_channels.add(task.channel_id.id)
                busy_pairs.add((task.channel_id.id, task.automation_id.id))
        for message in inbound:
            channel = message.channel_id
            if channel.ai_paused:
                continue
            route = channel._ai_agent_route(message.body) if router_enabled else False
            use_router = router_enabled and (
                not automations or route['route'] != 'general')
            if use_router:
                try:
                    with self.env.cr.savepoint():
                        if channel.id not in busy_channels:
                            task = tasks.create_from_channel(
                                channel, 'orchestrate', route['prompt'],
                                approval_required=True)
                            task.action_plan()
                            busy_channels.add(channel.id)
                            busy_pairs.add((channel.id, task.automation_id.id))
                            channel.message_post(
                                body=_('Agente IA: se preparó la ruta «%s» para revisión humana.') % route['label'],
                                subtype_xmlid='mail.mt_note',
                            )
                except Exception:  # noqa: BLE001 - no bloquear la recepción
                    _logger.exception(
                        'No se pudo preparar la ruta comercial del mensaje %s', message.id)
                continue
            if not automations:
                continue
            for automation in automations[:1]:
                try:
                    # El webhook no debe fallar porque una automatización tenga
                    # un error. La tarea queda auditada cuando puede crearse y
                    # el mensaje sigue disponible para el equipo humano.
                    with self.env.cr.savepoint():
                        if (channel.id, automation.id) in busy_pairs:
                            continue
                        task = tasks.create_from_channel(
                            channel, automation.task_type or 'followup',
                            automation.instruction or automation.name,
                            automation.approval_required,
                            automation=automation)
                        task.action_plan()
                        busy_channels.add(channel.id)
                        busy_pairs.add((channel.id, automation.id))

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

# -*- coding: utf-8 -*-
"""Orquestador de producción para conversaciones de Chatroom.

Este servicio es deliberadamente pequeño: decide qué flujo activar y delega
la operación en los modelos nativos de Odoo o en las capas especializadas de
Chatroom. No contiene una segunda implementación de Ventas, Calendario,
Facturación ni Pagos.
"""

import logging

from odoo import _, api, fields, models


_logger = logging.getLogger(__name__)


class ChatroomAiOrchestrator(models.AbstractModel):
    _name = 'chatroom.ai.orchestrator'
    _description = 'Orquestador operativo de Chatroom IA'

    @api.model
    def _param_enabled(self, key, default=False):
        value = self.env['ir.config_parameter'].sudo().get_param(key)
        if value in (False, None, ''):
            return default
        return str(value).strip().lower() in ('1', 'true', 'yes', 'on')

    @api.model
    def _existing_task(self, message):
        """Busca una tarea de este mensaje antes de crear otra.

        Los webhooks pueden reintentarse. La clave por mensaje evita que un
        reintento cree una segunda cotización, reunión o respuesta.
        """
        if 'chatroom.ai.task' not in self.env:
            return self.env['chatroom.ai.task'].browse()
        Task = self.env['chatroom.ai.task'].sudo()
        task = Task.search([('source_message_id', '=', message.id)], limit=1)
        if task:
            return task
        return Task.search([
            ('orchestration_key', '=', 'message:%s' % message.id),
        ], limit=1)

    @api.model
    def _create_task(self, message, route):
        task_model = self.env['chatroom.ai.task']
        task = task_model.create_from_channel(
            message.channel_id,
            task_type='orchestrate',
            prompt=route['prompt'],
            source_message=message,
            orchestration_key='message:%s' % message.id,
            route=route['route'],
        )
        task.action_plan()
        return task

    @api.model
    def _post_trace(self, channel, text, subtype='mail.mt_note'):
        try:
            channel.message_post(body=text, subtype_xmlid=subtype)
        except Exception:  # noqa: BLE001 - la trazabilidad nunca bloquea el webhook
            _logger.exception('No se pudo registrar la traza del orquestador')

    @api.model
    def _schedule_handoff_activity(self, channel, reason):
        """Create one native activity when the guard hands off to a person."""
        if not channel or 'mail.activity' not in self.env or 'ir.model' not in self.env:
            return False
        model = self.env['ir.model']._get('chatroom.channel')
        activity_type = self.env.ref(
            'mail.mail_activity_data_todo', raise_if_not_found=False)
        if not model or not activity_type:
            return False
        Activity = self.env['mail.activity'].sudo()
        summary = _('Revisión humana: Chatroom IA')
        existing = Activity.search([
            ('res_model_id', '=', model.id), ('res_id', '=', channel.id),
            ('activity_type_id', '=', activity_type.id),
            ('summary', '=', summary), ('user_id', '=', self.env.user.id),
        ], limit=1)
        if existing:
            return existing
        return Activity.create({
            'activity_type_id': activity_type.id,
            'res_model_id': model.id,
            'res_id': channel.id,
            'user_id': channel.assigned_user_id.id or self.env.user.id,
            'date_deadline': fields.Date.context_today(self),
            'summary': summary,
            'note': _('El agente IA detuvo la atención automática y solicita revisión humana.\nMotivo: %s') % (reason or _('No especificado')),
        })

    @api.model
    def process_inbound(self, messages):
        """Orquesta mensajes entrantes de producción.

        - Consulta, producto y disponibilidad: puede responder con la guardia
          existente cuando el modo automático está activado.
        - Cotización, reunión, cobro y cambios en Odoo: crea un plan auditable;
          las herramientas sensibles conservan aprobación humana.
        - Supervisado o simulación: prepara el plan, no envía ni modifica.
        """
        if not self._param_enabled('chatroom_ai_agent.production_orchestrator'):
            return messages

        icp = self.env['ir.config_parameter'].sudo()
        automatic = icp.get_param('chatroom_ai_agent.mode', 'supervised') == 'automatic'
        auto_reply = self._param_enabled(
            'chatroom_ai_agent.orchestrator_auto_reply', default=False)
        router_enabled = self._param_enabled(
            'chatroom_ai_agent.commercial_router_enabled', default=True)
        for message in messages.filtered(
                lambda item: item.direction == 'inbound' and item.channel_id):
            channel = message.channel_id
            if channel.ai_paused:
                continue
            if self._existing_task(message):
                continue
            try:
                route = channel._ai_agent_route(message.body) if router_enabled else {
                    'route': 'general',
                    'label': _('Consulta comercial'),
                    'prompt': _('Analiza la solicitud y prepara la siguiente respuesta útil con datos reales de Odoo.'),
                }
                sensitive = route['route'] in ('quote', 'meeting', 'payment')

                # Las operaciones que crean o envían documentos siempre pasan
                # por el motor de tareas y por la aprobación de cada herramienta.
                if sensitive or not (automatic and auto_reply):
                    task = self._create_task(message, route)
                    channel.sudo()._ai_set_orchestration_state(
                        route=route['route'], task=task,
                        state='waiting_confirmation' if task.state == 'awaiting_approval' else False)
                    if automatic and task.state == 'planned':
                        # Solo se ejecuta si las herramientas configuradas no
                        # exigen aprobación. Las herramientas nativas sensibles
                        # vienen protegidas por defecto.
                        task.action_run()
                    else:
                        self._post_trace(
                            channel,
                            _('Orquestador IA: ruta «%(route)s» preparada en %(task)s.') % {
                                'route': route['label'], 'task': task.display_name,
                            })
                    continue

                # Respuesta autónoma limitada: usa el guardia central de IA,
                # respetando horario, consentimiento, confianza, cooldown,
                # límite diario y escalamiento a humano.
                result = channel.action_ai_auto_reply_safe()
                result_status = result.get('status', '')
                if result_status in ('human_review', 'human_active', 'daily_limit',
                                     'cooldown', 'invalid_provider_response', 'opted_out'):
                    channel.sudo()._ai_set_orchestration_state(
                        route=route['route'], state='human',
                        reason=result.get('reason') or _('La guardia de IA solicitó revisión humana.'))
                    self._schedule_handoff_activity(
                        channel, result.get('reason') or _('La guardia de IA solicitó revisión humana.'))
                elif result_status == 'awaiting_approval':
                    channel.sudo()._ai_set_orchestration_state(
                        route=route['route'], state='waiting_confirmation')
                elif result_status == 'sent':
                    channel.sudo()._ai_set_orchestration_state(
                        route=route['route'], state='idle')
                self._post_trace(
                    channel,
                    _('Orquestador IA: %(route)s — %(status)s.') % {
                        'route': route['label'],
                        'status': result.get('status', _('sin resultado')),
                    })
            except Exception:  # noqa: BLE001 - un webhook no debe caerse por IA
                _logger.exception(
                    'Error en orquestación del mensaje entrante %s del canal %s',
                    message.id, channel.id)
        return messages

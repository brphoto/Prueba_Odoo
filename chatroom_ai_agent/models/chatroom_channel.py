# -*- coding: utf-8 -*-
import unicodedata

from odoo import _, fields, models
from odoo.exceptions import UserError


class ChatroomChannel(models.Model):
    _inherit = 'chatroom.channel'

    ai_flow_state = fields.Selection([
        ('idle', 'Disponible'),
        ('product', 'Consultando producto'),
        ('quote', 'Preparando cotización'),
        ('meeting', 'Coordinando reunión'),
        ('payment', 'Preparando pago'),
        ('waiting_confirmation', 'Esperando confirmación'),
        ('human', 'Atención humana'),
    ], string='Flujo IA', default='idle', index=True,
       help='Estado persistente del flujo comercial. No reemplaza la etapa de Chatroom: indica qué debe hacer el agente a continuación.')
    ai_last_route = fields.Selection([
        ('general', 'Consulta comercial'),
        ('product', 'Producto y disponibilidad'),
        ('quote', 'Cotización'),
        ('meeting', 'Reunión'),
        ('payment', 'Pago'),
    ], string='Última ruta IA', readonly=True, index=True)
    ai_pending_task_id = fields.Many2one(
        'chatroom.ai.task', string='Tarea IA pendiente', readonly=True,
        ondelete='set null', index=True)
    ai_handoff_reason = fields.Char(
        string='Motivo de escalamiento', readonly=True,
        help='Motivo resumido por el que la atención quedó en manos de una persona.')
    ai_last_agent_at = fields.Datetime(
        string='Última operación IA', readonly=True, index=True)

    def _ai_set_orchestration_state(self, route='general', task=False,
                                    state=False, reason=False):
        """Persist the small amount of state needed to resume a conversation.

        The task remains the audit trail; these fields are the operational
        snapshot used by the inbox and by the next inbound message.
        """
        self.ensure_one()
        valid_routes = {'general', 'product', 'quote', 'meeting', 'payment'}
        route = route if route in valid_routes else 'general'
        if not state:
            state = {
                'product': 'product', 'quote': 'quote',
                'meeting': 'meeting', 'payment': 'payment',
            }.get(route, 'idle')
        values = {
            'ai_last_route': route,
            'ai_flow_state': state,
            'ai_pending_task_id': task.id if task else False,
            'ai_handoff_reason': reason or False,
            'ai_last_agent_at': fields.Datetime.now(),
        }
        self.with_context(skip_ai_state_sync=True).write(values)
        return True

    def _ai_agent_route(self, message_text=False):
        """Detecta una ruta comercial inicial sin consumir tokens.

        Esta detección solo decide qué flujo preparar; nunca crea ni envía
        documentos por sí sola. La ejecución continúa protegida por las
        aprobaciones de cada herramienta.
        """
        self.ensure_one()
        text = (message_text or '').strip()
        if not text and 'message_ids' in self._fields:
            inbound = self.message_ids.filtered(
                lambda message: message.direction == 'inbound' and message.body
            ).sorted('date')
            text = inbound[-1].body if inbound else ''
        # La ruta nunca debe depender de que el navegador o el webhook haya
        # conservado las tildes. Se compara una versión normalizada, pero el
        # texto original sigue viajando al plan para conservar el español.
        normalized = ''.join(
            char for char in unicodedata.normalize('NFKD', text.lower())
            if not unicodedata.combining(char))
        patterns = (
            ('quote', ('cotizacion', 'presupuesto', 'propuesta', 'pdf')),
            ('meeting', ('reunion', 'cita', 'videollamada', 'meet', 'agenda')),
            ('payment', ('pagar', 'pago', 'cobrar', 'link de pago', 'enlace de pago')),
            ('product', ('producto', 'precio', 'cuanto cuesta', 'stock', 'disponibilidad', 'catalogo')),
        )
        route = 'general'
        for candidate, words in patterns:
            if any(word in normalized for word in words):
                route = candidate
                break
          # Si el cliente responde con un mensaje corto (por ejemplo «sí» o
          # «adelante») después de una cotización, reunión o pago, conserva el
          # flujo pendiente. Así el siguiente mensaje continúa la conversación
          # y no vuelve a caer en una consulta general.
        if route == 'general' and self.ai_flow_state in (
                'product', 'quote', 'meeting', 'payment', 'waiting_confirmation'):
            route = self.ai_last_route if self.ai_last_route in (
                'product', 'quote', 'meeting', 'payment') else 'general'
        labels = {
            'quote': _('Cotización y PDF'),
            'meeting': _('Reunión y enlace de Calendario'),
            'payment': _('Cobranza y link de pago'),
            'product': _('Producto, precio y disponibilidad'),
            'general': _('Consulta comercial'),
        }
        prompts = {
            'quote': _('Atiende la solicitud de cotización. Busca los productos reales mencionados, prepara una cotización nativa de Ventas y deja el PDF listo para aprobación y envío.'),
            'meeting': _('Atiende la solicitud de reunión. Usa Calendario nativo de Odoo, crea la actividad interna y prepara el enlace de videollamada para aprobación y envío.'),
            'payment': _('Consulta el documento pendiente y prepara el link del conector de pagos instalado. No cobres ni envíes sin aprobación.'),
            'product': _('Consulta el catálogo vivo de Odoo. Responde con nombre, precio vigente y disponibilidad; si no existe el producto, solicita aclaración o escala a un humano.'),
            'general': _('Analiza la solicitud, consulta el contexto comercial disponible y prepara la siguiente respuesta útil sin inventar datos.'),
        }
        return {'route': route, 'label': labels[route], 'prompt': prompts[route], 'message': text}

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
            'commercial_router_enabled': icp.get_param(
                'chatroom_ai_agent.commercial_router_enabled', 'False') == 'True',
            'route': self._ai_agent_route(),
            'flow_state': self.ai_flow_state or 'idle',
            'flow_state_label': dict(self._fields['ai_flow_state'].selection).get(
                self.ai_flow_state, _('Disponible')),
            'last_route': self.ai_last_route or '',
            'pending_task_id': self.ai_pending_task_id.id or False,
            'handoff_reason': self.ai_handoff_reason or '',
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

    def action_ai_agent_commercial_router(self):
        """Prepara un plan operativo a partir del último mensaje entrante."""
        self.ensure_one()
        route = self._ai_agent_route()
        task = self.env['chatroom.ai.task'].create_from_channel(
            self, task_type='orchestrate', prompt=route['prompt'])
        task.action_plan()
        self.message_post(
            body=_('Agente IA: ruta detectada «%(route)s». Se preparó la tarea %(task)s; las acciones sensibles quedan pendientes de aprobación.') % {
                'route': route['label'], 'task': task.display_name,
            },
            subtype_xmlid='mail.mt_note',
        )
        return {
            'type': 'ir.actions.act_window', 'name': _('Plan comercial IA'),
            'res_model': 'chatroom.ai.task', 'res_id': task.id,
            'views': [(False, 'form')], 'target': 'new',
        }

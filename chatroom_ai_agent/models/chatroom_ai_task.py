# -*- coding: utf-8 -*-
import json
import re
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ChatroomAiTaskAction(models.Model):
    _name = 'chatroom.ai.task.action'
    _description = 'Acción de una tarea IA'
    _order = 'sequence, id'

    task_id = fields.Many2one('chatroom.ai.task', string='Tarea', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    key = fields.Char(string='Clave', required=True)
    name = fields.Char(string='Nombre', required=True)
    state = fields.Selection([
        ('pending', 'Pendiente'), ('running', 'Ejecutando'),
        ('done', 'Completada'), ('skipped', 'Omitida'), ('error', 'Error'),
    ], default='pending', required=True, index=True)
    requires_approval = fields.Boolean(default=True)
    risk_level = fields.Selection([
        ('low', 'Bajo'), ('medium', 'Medio'), ('high', 'Alto'),
    ], string='Riesgo', compute='_compute_risk_level', store=True)
    input_json = fields.Text(string='Entrada')
    output_json = fields.Text(string='Salida', readonly=True)
    error_message = fields.Text(string='Error', readonly=True)

    @api.depends('key')
    def _compute_risk_level(self):
        high = {'send_whatsapp_reply', 'send_payment_link', 'create_quotation'}
        medium = {'create_lead', 'create_activity', 'prepare_payment_link'}
        for action in self:
            action.risk_level = 'high' if action.key in high else 'medium' if action.key in medium else 'low'


class ChatroomAiTask(models.Model):
    _name = 'chatroom.ai.task'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Tarea operativa del agente IA'
    _order = 'priority desc, create_date desc, id desc'

    name = fields.Char(string='Tarea', required=True, default=lambda self: _('Nueva tarea IA'), tracking=True)
    task_type = fields.Selection([
        ('orchestrate', 'Orquestar solicitud'),
        ('classify_customer', 'Clasificar cliente'),
        ('qualify_lead', 'Calificar oportunidad'),
        ('prepare_reply', 'Preparar respuesta'),
        ('followup', 'Preparar seguimiento'),
        ('collect_payment', 'Preparar cobranza'),
        ('sales_conversion', 'Convertir conversación en venta'),
        ('daily_review', 'Revisión diaria'),
    ], string='Tipo de tarea', required=True, default='orchestrate', index=True)
    state = fields.Selection([
        ('draft', 'Borrador'), ('awaiting_approval', 'Esperando aprobación'),
        ('planned', 'Planificada'), ('running', 'Ejecutando'),
        ('done', 'Completada'), ('failed', 'Fallida'), ('cancelled', 'Cancelada'),
    ], string='Estado', required=True, default='draft', index=True, tracking=True)
    priority = fields.Selection([('0', 'Normal'), ('1', 'Alta'), ('2', 'Urgente')], default='0', required=True)
    prompt = fields.Text(string='Solicitud')
    plan_json = fields.Text(string='Plan técnico', readonly=True)
    input_context = fields.Text(string='Contexto utilizado', readonly=True)
    knowledge_sources = fields.Text(string='Fuentes de conocimiento', readonly=True)
    knowledge_live_sources = fields.Text(string='Datos vivos consultados', readonly=True)
    knowledge_context_chars = fields.Integer(string='Caracteres de contexto', readonly=True)
    knowledge_estimated_input_tokens = fields.Integer(string='Tokens estimados de entrada', readonly=True)
    output_json = fields.Text(string='Resultado técnico', readonly=True)
    result_summary = fields.Text(string='Resumen del resultado', readonly=True)
    result_preview = fields.Text(
        string='Resultado para el agente', readonly=True,
        help='Resultado legible de las acciones ejecutadas. Las respuestas preparadas no se envían automáticamente.')
    error_message = fields.Text(string='Detalle del error', readonly=True)
    channel_id = fields.Many2one('chatroom.channel', string='Conversación', ondelete='cascade', index=True)
    partner_id = fields.Many2one(related='channel_id.partner_id', string='Cliente', store=True, readonly=True)
    user_id = fields.Many2one('res.users', string='Responsable', default=lambda self: self.env.user, index=True)
    company_id = fields.Many2one('res.company', string='Empresa', default=lambda self: self.env.company, index=True)
    automation_id = fields.Many2one('chatroom.ai.automation', string='Automatización de origen', readonly=True, index=True)
    playbook_id = fields.Many2one('chatroom.ai.playbook', string='Acción guardada de origen', readonly=True, index=True)
    approval_required = fields.Boolean(string='Requiere aprobación', default=True)
    risk_level = fields.Selection([
        ('low', 'Bajo'), ('medium', 'Medio'), ('high', 'Alto'),
    ], string='Nivel de riesgo', compute='_compute_risk_level', store=True)
    approved_by = fields.Many2one('res.users', readonly=True)
    approved_at = fields.Datetime(readonly=True)
    started_at = fields.Datetime(readonly=True)
    completed_at = fields.Datetime(readonly=True)
    next_run_at = fields.Datetime(default=fields.Datetime.now, index=True)
    attempts = fields.Integer(default=0, readonly=True)
    max_attempts = fields.Integer(default=3)
    active = fields.Boolean(default=True)
    action_ids = fields.One2many('chatroom.ai.task.action', 'task_id', string='Plan de acciones')
    audit_ids = fields.One2many('chatroom.ai.audit', 'task_id', string='Auditoría')

    operational_status = fields.Char(string='Estado operativo', compute='_compute_operational_status')
    action_progress = fields.Char(string='Progreso', compute='_compute_operational_status')

    @api.depends('state', 'action_ids.state', 'attempts', 'max_attempts', 'error_message')
    def _compute_operational_status(self):
        for task in self:
            total = len(task.action_ids)
            completed = len(task.action_ids.filtered(lambda action: action.state in ('done', 'skipped')))
            task.action_progress = _('%s/%s acciones completadas') % (completed, total)
            if task.state == 'draft':
                task.operational_status = _('Listo para generar el plan.')
            elif task.state == 'awaiting_approval':
                task.operational_status = _('Requiere aprobación humana antes de ejecutar.')
            elif task.state == 'planned':
                task.operational_status = _('Plan listo; pendiente de ejecución.')
            elif task.state == 'running':
                task.operational_status = _('Ejecutando acciones de forma controlada.')
            elif task.state == 'done':
                task.operational_status = _('Completada correctamente.')
            elif task.state == 'failed':
                task.operational_status = _('Falló en el intento %s de %s. Revisa el detalle o reintenta.') % (
                    task.attempts, task.max_attempts)
            else:
                task.operational_status = _('Cancelada; no se ejecutará.')

    @api.depends('task_type', 'action_ids.risk_level', 'state')
    def _compute_risk_level(self):
        defaults = {
            'collect_payment': 'high',
            'sales_conversion': 'high',
            'qualify_lead': 'medium',
            'followup': 'medium',
        }
        rank = {'low': 0, 'medium': 1, 'high': 2}
        for task in self:
            level = defaults.get(task.task_type, 'low')
            for action in task.action_ids:
                if rank.get(action.risk_level, 0) > rank.get(level, 0):
                    level = action.risk_level
            task.risk_level = level

    @api.constrains('max_attempts')
    def _check_max_attempts(self):
        for task in self:
            if task.max_attempts <= 0:
                raise ValidationError(_('Los intentos máximos deben ser mayores que cero.'))

    @api.model
    def _json(self, value):
        return json.dumps(value, ensure_ascii=False, indent=2, default=str)

    @api.model
    def create_from_channel(self, channel, task_type='orchestrate', prompt=False, approval_required=None, automation=False, playbook=False):
        channel.ensure_one()
        icp = self.env['ir.config_parameter'].sudo()
        mode = icp.get_param('chatroom_ai_agent.mode', 'supervised')
        if approval_required is None:
            configured = icp.get_param('chatroom_ai_agent.require_approval', 'True')
            approval_required = str(configured).strip().lower() in ('1', 'true', 'yes', 'on')
        if mode in ('supervised', 'simulation'):
            approval_required = True
        task = self.create({
            'name': _('IA: %s') % channel.display_name,
            'task_type': task_type,
            'prompt': prompt or _('Analiza esta conversación y determina la siguiente acción útil.'),
            'channel_id': channel.id,
            'company_id': channel.company_id.id if 'company_id' in channel._fields and channel.company_id else self.env.company.id,
            'approval_required': approval_required,
            'max_attempts': automation.max_attempts if automation and automation.max_attempts else 3,
            'user_id': self.env.user.id,
            'automation_id': automation.id if automation else False,
            'playbook_id': playbook.id if playbook else False,
        })
        return task

    def _context(self):
        self.ensure_one()
        channel = self.channel_id
        partner = self.partner_id
        data = {
            'task': self.prompt or '',
            'task_type': self.task_type,
            'channel': channel.display_name if channel else False,
            'partner': partner.display_name if partner else False,
            'messages': len(channel.message_ids) if channel and 'message_ids' in channel._fields else 0,
            'recent_messages': [
                {
                    'direction': message.direction,
                    'body': (message.body or '')[:500],
                    'date': fields.Datetime.to_string(message.date) if message.date else False,
                }
                for message in (channel.message_ids.sorted('date')[-channel._ai_history_limit():] if channel and 'message_ids' in channel._fields else [])
                if message.body
            ],
        }
        for field_name in ('rfm_category', 'rfm_score', 'rfm_total_amount', 'rfm_last_invoice_date'):
            if partner and field_name in partner._fields:
                data[field_name] = partner[field_name]
        if partner and 'crm.lead' in self.env and 'partner_id' in self.env['crm.lead']._fields:
            opportunities = self.env['crm.lead'].search([
                ('partner_id', '=', partner.id), ('type', '=', 'opportunity'), ('active', '=', True),
                ('company_id', '=', self.company_id.id),
            ], order='write_date desc, id desc', limit=10)
            data['open_opportunities'] = [{
                'id': lead.id,
                'name': lead.display_name,
                'stage': lead.stage_id.display_name if 'stage_id' in lead._fields and lead.stage_id else False,
                'expected_revenue': lead.expected_revenue if 'expected_revenue' in lead._fields else 0,
            } for lead in opportunities]
        if partner and 'sale.order' in self.env:
            orders = self.env['sale.order'].search([
                ('partner_id', '=', partner.id), ('state', 'in', ('draft', 'sent', 'sale')),
                ('company_id', '=', self.company_id.id),
            ], order='date_order desc, id desc', limit=10)
            data['sales_documents'] = [{
                'id': order.id,
                'name': order.name,
                'state': order.state,
                'amount_total': order.amount_total,
            } for order in orders]
        if partner and 'account.move' in self.env:
            invoices = self.env['account.move'].search([
                ('partner_id', '=', partner.id), ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'), ('payment_state', 'in', ('not_paid', 'partial')),
                ('company_id', '=', self.company_id.id),
            ], order='invoice_date_due asc, id desc', limit=10)
            data['open_invoices'] = [{
                'id': invoice.id,
                'name': invoice.name,
                'amount_residual': invoice.amount_residual,
                'due_date': fields.Date.to_string(invoice.invoice_date_due) if invoice.invoice_date_due else False,
            } for invoice in invoices]
        # La base comercial es opcional: el agente funciona sin ella, pero si
        # está instalada cada tarea recibe el conocimiento relevante y las
        # fuentes vivas de Odoo sin tener que enviar todo el catálogo al modelo.
        if 'ai.knowledge.base' in self.env:
            try:
                knowledge = self.env['ai.knowledge.base'].get_sales_context_details(
                    channel=channel,
                    query=self.prompt or '',
                    partner=partner,
                    company=self.company_id,
                )
                data['knowledge_context'] = knowledge.get('context', '')
                data['knowledge_sources'] = knowledge.get('sources', [])
                data['knowledge_live_sources'] = knowledge.get('live_sources', [])
                data['knowledge_estimated_input_tokens'] = knowledge.get('estimated_input_tokens', 0)
            except Exception:
                # Una base de conocimiento incompleta no debe impedir una
                # clasificación, seguimiento o respuesta segura.
                data['knowledge_context'] = ''
        return data

    def _fallback_plan(self):
        self.ensure_one()
        plans = {
            'classify_customer': [('classify_customer', 'Leer clasificación comercial del cliente')],
            'qualify_lead': [('classify_customer', 'Leer clasificación comercial del cliente'), ('create_lead', 'Crear o actualizar oportunidad')],
            'sales_conversion': [
                ('search_catalog', 'Buscar productos relacionados'),
                ('classify_intent', 'Identificar intención comercial'),
                ('create_lead', 'Crear oportunidad desde la conversación'),
                ('create_quotation', 'Crear cotización para el cliente'),
                ('create_activity', 'Registrar seguimiento comercial'),
            ],
            'prepare_reply': [('classify_intent', 'Identificar intención'), ('prepare_reply', 'Preparar respuesta sin enviarla')],
            'followup': [
                ('classify_intent', 'Identificar intención'),
                ('prepare_reply', 'Preparar seguimiento personalizado'),
                ('create_activity', 'Registrar seguimiento pendiente'),
            ],
            'collect_payment': [('find_open_invoice', 'Consultar facturas pendientes'), ('send_payment_link', 'Generar y enviar link de pago')],
            'daily_review': [('classify_customer', 'Revisar clasificación de clientes'), ('classify_intent', 'Revisar intención de conversaciones')],
            'orchestrate': [('classify_customer', 'Revisar contexto comercial'), ('classify_intent', 'Identificar intención'), ('prepare_reply', 'Proponer siguiente acción')],
        }
        return [{'key': key, 'name': name} for key, name in plans.get(self.task_type, plans['orchestrate'])]

    def _ai_plan(self, context):
        self.ensure_one()
        # El plan local cubre las tareas operativas conocidas y no consume
        # tokens. El planificador externo se habilita explícitamente desde
        # Ajustes > Agente IA cuando se necesite razonamiento adicional.
        if self.env['ir.config_parameter'].sudo().get_param(
                'chatroom_ai_agent.ai_planning_enabled', 'False') != 'True':
            return False
        channel = self.channel_id
        if not channel or not hasattr(channel, '_ai_get_credentials') or not channel._ai_get_credentials():
            return False
        prompt = _('''Devuelve únicamente JSON válido con esta forma: {"actions":[{"key":"...","name":"..."}]}.
Usa solo estas herramientas: classify_customer, classify_intent, prepare_reply, create_lead,
search_catalog, create_quotation, find_open_invoice, prepare_payment_link, create_activity. No envíes mensajes
ni ejecutes pagos. La cotización y las actividades requieren aprobación humana.
Solicitud: %s
Contexto: %s''') % (self.prompt or '', self._json(context))
        try:
            raw = channel._ai_chat_completion([{'role': 'user', 'content': prompt}], task_type='agent')
            parsed = json.loads(raw)
            actions = parsed.get('actions', [])
            allowed = {tool.key for tool in self.env['chatroom.ai.tool'].enabled_for_user()}
            result = [a for a in actions if a.get('key') in allowed and a.get('name')]
            return result or False
        except Exception:
            return False

    def action_plan(self):
        for task in self:
            if task.state not in ('draft', 'failed'):
                continue
            context = task._context()
            actions = task._ai_plan(context) or task._fallback_plan()
            task.action_ids.sudo().unlink()
            max_actions_value = self.env['ir.config_parameter'].sudo().get_param('chatroom_ai_agent.max_actions', '8') or '8'
            try:
                max_actions = max(int(max_actions_value), 1)
            except (TypeError, ValueError):
                max_actions = 8
            for index, action in enumerate(actions[:max(max_actions, 1)], 1):
                tool = self.env['chatroom.ai.tool'].search([('key', '=', action['key']), ('active', '=', True)], limit=1)
                task.env['chatroom.ai.task.action'].create({
                    'task_id': task.id, 'sequence': index * 10,
                    'key': action['key'], 'name': action['name'],
                    'requires_approval': tool.requires_approval if tool else True,
                    'input_json': task._json(context),
                })
            needs_approval = task.approval_required or any(
                line.requires_approval for line in task.action_ids)
            task.write({
                'approval_required': needs_approval,
                'state': 'awaiting_approval' if needs_approval else 'planned',
                'plan_json': task._json({'actions': actions}),
                'input_context': task._json(context),
                'knowledge_sources': '\n'.join(
                    '- %s (v%s)' % (item.get('name') or 'Fuente', item.get('version', 1))
                    for item in context.get('knowledge_sources', []) if item.get('name')),
                'knowledge_live_sources': '\n'.join(
                    '- %s' % item for item in context.get('knowledge_live_sources', []) if item),
                'knowledge_context_chars': len(context.get('knowledge_context', '') or ''),
                'knowledge_estimated_input_tokens': context.get('knowledge_estimated_input_tokens', 0),
                'error_message': False,
            })
            task._audit('Plan generado', 'done', message=_('Se generó un plan de %s acción(es).') % len(actions))
        return True

    def _audit(self, name, state, action=False, message=False, output=False):
        self.ensure_one()
        return self.env['chatroom.ai.audit'].sudo().create({
            'name': name, 'task_id': self.id,
            'action_id': action.id if action else False,
            'tool_id': self.env['chatroom.ai.tool'].search([('key', '=', action.key)], limit=1).id if action else False,
            'state': state, 'message': message or False,
            'input_json': action.input_json if action else self.input_context,
            'output_json': output or (action.output_json if action else False),
        })

    @api.model
    def _build_result_preview(self, outputs):
        """Convert technical action output into a useful human summary."""
        lines = []
        for output in outputs or []:
            if output.get('status') == 'skipped':
                lines.append(_('Omitida: %s') % (output.get('reason') or _('no aplica')))
                continue
            if output.get('status') == 'blocked':
                lines.append(_('Bloqueada: %s') % (output.get('reason') or _('requiere revisión')))
                continue
            if output.get('reply'):
                lines.append(_('Respuesta preparada (no enviada):\n%s') % output['reply'])
            elif output.get('category') is not None:
                lines.append(_('Cliente clasificado: categoría %s, score %s.') % (
                    output.get('category') or _('sin historial'), output.get('score', 0)))
            elif output.get('intent'):
                lines.append(_('Intención identificada: %s.') % output['intent'])
            elif output.get('lead_name'):
                lines.append(_('Oportunidad disponible: %s.') % output['lead_name'])
            elif output.get('order_name'):
                lines.append(_('Cotización disponible: %s.') % output['order_name'])
            elif output.get('link_id'):
                lines.append(_('Enlace de pago preparado: %s.') % output.get('document', _('documento')))
            elif output.get('invoices') is not None:
                lines.append(_('Facturas pendientes encontradas: %s.') % len(output['invoices']))
            elif output.get('matches') is not None:
                lines.append(_('Productos encontrados en el catálogo: %s.') % len(output['matches']))
            else:
                lines.append(_('Acción completada: %s.') % (output.get('action') or _('operación')))
        return '\n\n'.join(lines) or _('No se generó un resultado visible.')

    def _execute_action(self, action):
        self.ensure_one()
        channel = self.channel_id
        partner = self.partner_id
        result = {'action': action.key, 'status': 'completed'}
        if action.key == 'classify_customer':
            result.update({
                'category': partner.rfm_category if partner and 'rfm_category' in partner._fields else 'sin_historial',
                'score': partner.rfm_score if partner and 'rfm_score' in partner._fields else 0,
            })
        elif action.key == 'classify_intent':
            result['intent'] = channel.ai_intent if channel and 'ai_intent' in channel._fields and channel.ai_intent else 'otro'
        elif action.key in ('prepare_reply',):
            if channel and hasattr(channel, '_ai_get_credentials') and channel._ai_get_credentials():
                result['reply'] = channel._ai_chat_completion(channel._ai_build_conversation(extra_system=self.prompt or _('Prepara una respuesta breve y profesional.')), task_type='reply')
            else:
                result['reply'] = _('Se preparó la tarea. Configure el proveedor de IA para generar el texto personalizado.')
        elif action.key == 'create_lead':
            if 'crm.lead' not in self.env or not partner:
                result['status'] = 'skipped'
                result['reason'] = _('CRM o cliente no disponible.')
            else:
                lead = self.env['crm.lead'].search([
                    ('partner_id', '=', partner.id), ('type', '=', 'opportunity'),
                    ('active', '=', True), ('company_id', '=', self.company_id.id),
                ], order='write_date desc, id desc', limit=1)
                action_result = False
                if not lead and channel and hasattr(channel, 'action_create_lead'):
                    action_result = channel.action_create_lead()
                    lead = self.env['crm.lead'].browse(
                        action_result.get('res_id')).exists() if action_result else self.env['crm.lead'].browse()
                if not lead:
                    lead = self.env['crm.lead'].create({
                        'name': _('Oportunidad IA - %s') % partner.display_name,
                        'partner_id': partner.id, 'type': 'opportunity',
                        'company_id': self.company_id.id,
                    })
                result['lead_id'] = lead.id
                result['lead_name'] = lead.display_name
        elif action.key == 'search_catalog':
            if 'product.template' not in self.env:
                result['status'] = 'skipped'
                result['reason'] = _('El catálogo de productos no está disponible.')
            else:
                message_text = ' '.join([
                    self.prompt or '',
                    ' '.join((message.body or '') for message in channel.message_ids if message.body) if channel else '',
                ])
                stopwords = {
                    'para', 'como', 'esta', 'este', 'cliente', 'cotización', 'cotizacion',
                    'producto', 'productos', 'quiero', 'necesito', 'desde', 'con', 'una', 'uno',
                    'del', 'por', 'que', 'los', 'las', 'una', 'sus', 'the', 'and',
                }
                terms = [term for term in re.findall(r'[\wáéíóúñü]{3,}', message_text.lower()) if term not in stopwords]
                products = self.env['product.template'].browse()
                for term in terms[:3]:
                    products |= self.env['product.template'].search([
                        ('active', '=', True), '|', ('name', 'ilike', term), ('default_code', 'ilike', term),
                    ], limit=5)
                if not products:
                    products = self.env['product.template'].search([('active', '=', True)], order='write_date desc, id desc', limit=5)
                result['matches'] = [{
                    'id': product.id,
                    'name': product.display_name,
                    'default_code': product.default_code or False,
                    'list_price': product.list_price,
                } for product in products[:10]]
                result['search_terms'] = terms[:3]
        elif action.key == 'create_quotation':
            if 'sale.order' not in self.env or not channel or not partner:
                result['status'] = 'skipped'
                result['reason'] = _('Ventas, conversación o cliente no disponible.')
            elif not hasattr(channel, 'action_create_quotation'):
                result['status'] = 'skipped'
                result['reason'] = _('El conector de ventas no está instalado.')
            else:
                order = channel.ai_sales_last_order_id if 'ai_sales_last_order_id' in channel._fields else self.env['sale.order'].browse()
                if not order or order.state not in ('draft', 'sent', 'sale'):
                    order = self.env['sale.order'].search([
                        ('partner_id', '=', partner.id),
                        ('origin', '=', channel.display_name),
                        ('state', 'in', ('draft', 'sent', 'sale')),
                        ('company_id', '=', self.company_id.id),
                    ], order='write_date desc, id desc', limit=1)
                if not order:
                    action_result = channel.action_create_quotation()
                    order = self.env['sale.order'].browse(action_result.get('res_id')).exists()
                if not order:
                    result['status'] = 'skipped'
                    result['reason'] = _('No se pudo crear la cotización.')
                else:
                    result.update({'order_id': order.id, 'order_name': order.name, 'state': order.state})
        elif action.key == 'find_open_invoice':
            if 'account.move' not in self.env or not partner:
                result['invoices'] = []
            else:
                invoices = self.env['account.move'].search([
                    ('partner_id', '=', partner.id), ('move_type', '=', 'out_invoice'),
                    ('state', '=', 'posted'), ('payment_state', 'in', ('not_paid', 'partial')),
                    ('company_id', '=', self.company_id.id),
                ], limit=20)
                result['invoices'] = [{'id': inv.id, 'name': inv.name, 'amount_residual': inv.amount_residual} for inv in invoices]
        elif action.key == 'prepare_payment_link':
            result['status'] = 'ready_for_connector' if 'payment.link' in self.env or 'chatroom.payment.link' in self.env else 'requires_payment_module'
            result['message'] = _('La generación final del link requiere el conector de pagos instalado y autorizado.')
        elif action.key == 'send_payment_link':
            if not channel or 'chatroom.payment.link' not in self.env or not hasattr(channel, 'action_send_payment_link'):
                result['status'] = 'skipped'
                result['reason'] = _('Instala Chatroom Payment para usar este conector.')
            elif 'sale.order' not in self.env and 'account.move' not in self.env:
                result['status'] = 'skipped'
                result['reason'] = _('No existe un modelo de documento cobrable.')
            else:
                document = self.env['sale.order'].search([
                    ('partner_id', '=', partner.id),
                    ('state', 'in', ('draft', 'sent', 'sale')),
                    ('company_id', '=', self.company_id.id),
                ], order='date_order desc, id desc', limit=1) if partner and 'sale.order' in self.env else self.env['account.move'].browse()
                if not document and partner and 'account.move' in self.env:
                    document = self.env['account.move'].search([
                        ('partner_id', '=', partner.id),
                        ('move_type', '=', 'out_invoice'),
                        ('state', '=', 'posted'),
                        ('payment_state', 'in', ('not_paid', 'partial')),
                        ('company_id', '=', self.company_id.id),
                    ], order='invoice_date desc, id desc', limit=1)
                if not document:
                    result['status'] = 'skipped'
                    result['reason'] = _('No hay un presupuesto, pedido o factura pendiente para cobrar.')
                else:
                    limit_value = self.env['ir.config_parameter'].sudo().get_param('chatroom_ai_agent.max_payment_amount', '0') or '0'
                    try:
                        limit = float(limit_value)
                    except (TypeError, ValueError):
                        limit = 0.0
                    amount = document.amount_total if 'amount_total' in document._fields else 0.0
                    if limit > 0 and amount > limit:
                        result['status'] = 'blocked'
                        result['reason'] = _('El documento supera el límite de cobro automático configurado (%s).') % limit
                        return result
                    link = self.env['chatroom.payment.link'].search([
                        ('channel_id', '=', channel.id),
                        ('res_model', '=', document._name), ('res_id', '=', document.id),
                        ('state', 'in', ('generated', 'sent', 'paid')),
                    ], order='create_date desc, id desc', limit=1)
                    if not link:
                        channel.action_send_payment_link(document._name, document.id)
                        link = self.env['chatroom.payment.link'].search([
                            ('channel_id', '=', channel.id),
                            ('res_model', '=', document._name), ('res_id', '=', document.id),
                        ], order='create_date desc, id desc', limit=1)
                    result.update({
                        'document': document.display_name,
                        'provider': link.provider_id.display_name if link.provider_id else _('Pago en línea'),
                        'link_id': link.id,
                        'state': link.state,
                    })
        elif action.key == 'create_activity':
            if 'mail.activity' not in self.env or not channel:
                result['status'] = 'skipped'
            else:
                model = self.env['ir.model']._get('chatroom.channel')
                activity_type = self.env['mail.activity.type'].search([], limit=1)
                if model and activity_type:
                    activity = self.env['mail.activity'].create({'res_model_id': model.id, 'res_id': channel.id, 'activity_type_id': activity_type.id, 'summary': self.name, 'user_id': self.user_id.id})
                    result['activity_id'] = activity.id
        elif action.key == 'send_whatsapp_reply':
            if not channel or not hasattr(channel, 'action_send_text'):
                result['status'] = 'skipped'
            else:
                reply = ''
                previous = self.action_ids.filtered(
                    lambda line: line.key == 'prepare_reply' and line.state == 'done')[-1:]
                if previous and previous.output_json:
                    try:
                        reply = json.loads(previous.output_json).get('reply', '')
                    except (TypeError, ValueError):
                        reply = ''
                if not reply:
                    result['status'] = 'blocked'
                    result['reason'] = _('No existe un texto aprobado para enviar.')
                else:
                    channel.with_context(chatroom_ai_generated=True).action_send_text(reply)
        return result

    def action_approve(self):
        for task in self:
            if task.state != 'awaiting_approval':
                continue
            task.write({'state': 'planned', 'approved_by': self.env.user.id, 'approved_at': fields.Datetime.now(), 'error_message': False})
            task._audit('Plan aprobado', 'done', message=_('Aprobado por %s.') % self.env.user.display_name)
        return True

    def action_run(self):
        for task in self:
            if task.state == 'draft':
                task.action_plan()
            if task.state == 'awaiting_approval':
                raise UserError(_('Esta tarea necesita aprobación antes de ejecutarse.'))
            if task.state not in ('planned', 'failed'):
                continue
            if self.env['ir.config_parameter'].sudo().get_param('chatroom_ai_agent.mode', 'supervised') == 'simulation':
                task.write({
                    'state': 'done', 'completed_at': fields.Datetime.now(),
                    'result_summary': _('Simulación: no se modificaron datos ni se enviaron mensajes.'),
                    'result_preview': _('Modo simulación: el plan se validó, pero no ejecutó cambios ni envió mensajes.'),
                })
                continue
            task.write({'state': 'running', 'started_at': fields.Datetime.now(), 'attempts': task.attempts + 1})
            try:
                outputs = []
                for action in task.action_ids.filtered(lambda line: line.state in ('pending', 'error')):
                    if action.requires_approval and not task.approved_by:
                        raise UserError(_('La acción "%s" requiere aprobación humana.') % action.name)
                    action.write({'state': 'running', 'error_message': False})
                    try:
                        output = task._execute_action(action)
                        if output.get('status') == 'blocked':
                            action.write({'state': 'error', 'output_json': task._json(output), 'error_message': output.get('reason')})
                            raise UserError(output.get('reason') or _('La política de seguridad bloqueó esta acción.'))
                        action.write({'state': 'done' if output.get('status') != 'skipped' else 'skipped', 'output_json': task._json(output)})
                        task._audit(action.name, 'done', action=action, output=task._json(output))
                        outputs.append(output)
                    except Exception as exc:
                        action.write({'state': 'error', 'error_message': str(exc)})
                        task._audit(action.name, 'error', action=action, message=str(exc))
                        raise
                task.write({
                    'state': 'done', 'completed_at': fields.Datetime.now(),
                    'output_json': task._json(outputs),
                    'result_summary': _('Se completaron %s acción(es).') % len(outputs),
                    'result_preview': self._build_result_preview(outputs),
                    'error_message': False,
                })
                if task.partner_id:
                    self.env['chatroom.ai.memory'].sudo().remember(task.result_summary, partner=task.partner_id, channel=task.channel_id, memory_type='outcome', source='agent')
            except Exception as exc:
                task.write({'state': 'failed', 'error_message': str(exc)})
                if task.attempts >= task.max_attempts:
                    task._audit('Tarea bloqueada', 'blocked', message=_('Se alcanzó el máximo de intentos.'))
                else:
                    task._audit('Tarea fallida', 'error', message=str(exc))
                raise UserError(_('La tarea IA falló: %s') % exc)
        return True

    def action_retry(self):
        self.write({
            'state': 'planned', 'error_message': False,
            'result_preview': False, 'next_run_at': fields.Datetime.now(),
        })
        self.action_ids.filtered(lambda line: line.state == 'error').write({'state': 'pending', 'error_message': False})
        return True

    def action_run_selected(self):
        """Run only selected planned tasks and keep approval gates intact."""
        planned = self.filtered(lambda task: task.state == 'planned')
        completed = 0
        failed = 0
        for task in planned:
            try:
                with self.env.cr.savepoint():
                    task.action_run()
                completed += 1
            except UserError:
                failed += 1
        skipped = len(self) - len(planned)
        message = _('Ejecutadas: %s. Con error: %s. Omitidas por estado: %s.') % (completed, failed, skipped)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': _('Centro de control IA'), 'message': message, 'type': 'success' if not failed else 'warning', 'sticky': False},
        }

    def action_retry_selected(self):
        """Prepare only selected failed tasks for another controlled run."""
        failed = self.filtered(lambda task: task.state == 'failed')
        failed.action_retry()
        skipped = len(self) - len(failed)
        message = _('Listas para reintentar: %s. Omitidas por estado: %s.') % (len(failed), skipped)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': _('Centro de control IA'), 'message': message, 'type': 'success', 'sticky': False},
        }

    def action_cancel(self):
        self.write({'state': 'cancelled'})
        return True

    @api.model
    def _cron_run_pending(self):
        candidates = self.sudo().search([
            ('state', 'in', ('draft', 'planned')), ('active', '=', True),
            ('next_run_at', '<=', fields.Datetime.now()),
        ], limit=50)
        tasks = candidates.filtered(
            lambda task: task.attempts < max(task.max_attempts or 1, 1))[:20]
        for task in tasks:
            try:
                with self.env.cr.savepoint():
                    if task.state == 'draft':
                        task.action_plan()
                    if task.state != 'planned':
                        continue
                    task.action_run()
            except Exception as exc:  # noqa: BLE001 - el cron debe continuar con la cola
                # El savepoint revierte la ejecución parcial, pero el estado
                # de fallo se registra fuera de él para que el siguiente cron
                # no repita silenciosamente la misma tarea.
                failed_task = self.sudo().browse(task.id).exists()
                if failed_task:
                    attempts = failed_task.attempts + 1
                    failed_task.write({
                        'state': 'failed',
                        'attempts': attempts,
                        'error_message': str(exc)[:4000],
                        'next_run_at': fields.Datetime.now() + timedelta(
                            minutes=min(60, 5 * (2 ** max(attempts - 1, 0)))),
                    })
        return len(tasks)

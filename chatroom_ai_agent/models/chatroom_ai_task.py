# -*- coding: utf-8 -*-
import json
import re
import unicodedata
from datetime import datetime, time, timedelta

import pytz
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ChatroomAiTaskAction(models.Model):
    _name = 'chatroom.ai.task.action'
    _description = 'Acción de una tarea IA'
    _order = 'sequence, id'

    task_id = fields.Many2one('chatroom.ai.task', string='Tarea', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    tool_id = fields.Many2one(
        'chatroom.ai.tool', string='Acción disponible',
        domain=[('active', '=', True)],
        help='Selecciona una herramienta autorizada. La clave y el nombre se completan automáticamente.')
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

    @api.onchange('tool_id')
    def _onchange_tool_id(self):
        for action in self:
            if action.tool_id:
                action.key = action.tool_id.key
                action.name = action.tool_id.name
                action.requires_approval = action.tool_id.requires_approval

    @api.onchange('key')
    def _onchange_key(self):
        for action in self:
            if action.key:
                tool = self.env['chatroom.ai.tool'].search([('key', '=', action.key)], limit=1)
                if tool:
                    action.tool_id = tool
                    if not action.name:
                        action.name = tool.name

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            tool = self.env['chatroom.ai.tool'].browse(vals.get('tool_id')).exists()
            if not tool and vals.get('key'):
                tool = self.env['chatroom.ai.tool'].search([('key', '=', vals['key'])], limit=1)
            if tool:
                vals['tool_id'] = tool.id
                vals['key'] = tool.key
                if not vals.get('name'):
                    vals['name'] = tool.name
                if 'requires_approval' not in vals:
                    vals['requires_approval'] = tool.requires_approval
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('tool_id'):
            tool = self.env['chatroom.ai.tool'].browse(vals['tool_id']).exists()
            if tool:
                vals = dict(vals)
                vals.update({
                    'key': tool.key,
                    'name': tool.name,
                    'requires_approval': tool.requires_approval,
                })
        elif vals.get('key'):
            tool = self.env['chatroom.ai.tool'].search([('key', '=', vals['key'])], limit=1)
            if tool:
                vals = dict(vals)
                vals['tool_id'] = tool.id
        return super().write(vals)

    @api.depends('key')
    def _compute_risk_level(self):
        high = {
            'send_whatsapp_reply',
            'send_payment_link',
            'create_quotation',
            'send_quotation_pdf',
            'create_meeting',
        }
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
    result_model = fields.Char(
        string='Modelo del resultado', readonly=True,
        help='Modelo nativo de Odoo creado o consultado por la última ejecución.')
    result_res_id = fields.Integer(
        string='ID del resultado', readonly=True,
        help='Identificador del documento nativo relacionado con el resultado.')
    result_document_name = fields.Char(
        string='Documento generado', readonly=True)
    error_message = fields.Text(string='Detalle del error', readonly=True)
    channel_id = fields.Many2one('chatroom.channel', string='Conversación', ondelete='cascade', index=True)
    partner_id = fields.Many2one(related='channel_id.partner_id', string='Cliente', store=True, readonly=True)
    user_id = fields.Many2one('res.users', string='Responsable', default=lambda self: self.env.user, index=True)
    company_id = fields.Many2one('res.company', string='Empresa', default=lambda self: self.env.company, index=True)
    automation_id = fields.Many2one('chatroom.ai.automation', string='Automatización de origen', readonly=True, index=True)
    playbook_id = fields.Many2one('chatroom.ai.playbook', string='Acción guardada de origen', readonly=True, index=True)
    source_message_id = fields.Many2one(
        'chatroom.message', string='Mensaje que activó la tarea', readonly=True,
        index=True, ondelete='set null')
    orchestration_key = fields.Char(
        string='Clave de idempotencia', readonly=True, index=True,
        help='Evita duplicar tareas si el webhook de entrada se reintenta.')
    orchestration_route = fields.Selection([
        ('general', 'Consulta comercial'),
        ('product', 'Producto y disponibilidad'),
        ('quote', 'Cotización'),
        ('meeting', 'Reunión'),
        ('payment', 'Pago'),
    ], string='Ruta del orquestador', readonly=True, index=True)
    approval_required = fields.Boolean(string='Requiere aprobación', default=True)
    risk_level = fields.Selection([
        ('low', 'Bajo'), ('medium', 'Medio'), ('high', 'Alto'),
    ], string='Nivel de riesgo', compute='_compute_risk_level', store=True)
    approved_by = fields.Many2one('res.users', string='Aprobado por', readonly=True)
    approved_at = fields.Datetime(string='Aprobado el', readonly=True)
    started_at = fields.Datetime(string='Iniciada el', readonly=True)
    completed_at = fields.Datetime(string='Completada el', readonly=True)
    next_run_at = fields.Datetime(string='Próxima ejecución', default=fields.Datetime.now, index=True)
    attempts = fields.Integer(string='Intentos realizados', default=0, readonly=True)
    max_attempts = fields.Integer(string='Intentos máximos', default=3)
    active = fields.Boolean(string='Activa', default=True)
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

    def _sync_channel_state(self, state=False, reason=False):
        """Keep the inbox snapshot synchronized with the auditable task."""
        self.ensure_one()
        channel = self.channel_id
        if not channel or not hasattr(channel, '_ai_set_orchestration_state'):
            return
        route = self.orchestration_route or 'general'
        if state == 'awaiting_approval':
            flow_state = 'waiting_confirmation'
        elif state in ('failed', 'cancelled'):
            flow_state = 'human' if state == 'failed' else 'idle'
        elif state == 'done':
            flow_state = 'idle'
        else:
            flow_state = {
                'product': 'product', 'quote': 'quote',
                'meeting': 'meeting', 'payment': 'payment',
            }.get(route, 'idle')
        channel.sudo()._ai_set_orchestration_state(
            route=route, task=False if flow_state == 'idle' else self,
            state=flow_state, reason=reason)

    def _schedule_approval_activity(self):
        """Create one native Odoo activity to make approval actionable."""
        self.ensure_one()
        if self.state != 'awaiting_approval' or 'mail.activity' not in self.env:
            return False
        activity_type = self.env.ref(
            'mail.mail_activity_data_todo', raise_if_not_found=False)
        model = self.env['ir.model']._get(self._name)
        if not activity_type or not model:
            return False
        activity_model = self.env['mail.activity'].sudo()
        existing = activity_model.search([
            ('res_model_id', '=', model.id), ('res_id', '=', self.id),
            ('activity_type_id', '=', activity_type.id),
            ('user_id', '=', (self.user_id or self.env.user).id),
        ], limit=1)
        if existing:
            return existing
        return activity_model.create({
            'activity_type_id': activity_type.id,
            'res_model_id': model.id,
            'res_id': self.id,
            'user_id': (self.user_id or self.env.user).id,
            'date_deadline': fields.Date.context_today(self),
            'summary': _('Revisar plan del agente IA'),
            'note': _('La tarea %s tiene acciones que requieren aprobación humana. Revisa el plan, el riesgo y el resultado antes de ejecutar.') % self.display_name,
        })

    def _close_approval_activity(self):
        """Complete the native reminder once the plan is approved or done."""
        self.ensure_one()
        if 'mail.activity' not in self.env or 'ir.model' not in self.env:
            return False
        model = self.env['ir.model']._get(self._name)
        activity_type = self.env.ref(
            'mail.mail_activity_data_todo', raise_if_not_found=False)
        if not model or not activity_type:
            return False
        activities = self.env['mail.activity'].sudo().search([
            ('res_model_id', '=', model.id), ('res_id', '=', self.id),
            ('activity_type_id', '=', activity_type.id),
            ('summary', '=', _('Revisar plan del agente IA')),
        ])
        if activities:
            try:
                activities.action_done()
            except Exception:  # noqa: BLE001 - no bloquear la aprobación
                activities.unlink()
        return True

    def _store_native_result(self, outputs):
        """Expose the native Odoo record produced by the task in one click."""
        self.ensure_one()
        priorities = (
            ('order_id', 'sale.order', 'order_name'),
            ('event_id', 'calendar.event', 'meeting_name'),
            ('link_id', 'chatroom.payment.link', 'document'),
            ('activity_id', 'mail.activity', False),
            ('lead_id', 'crm.lead', 'lead_name'),
        )
        for key, model, name_key in priorities:
            for output in reversed(outputs or []):
                res_id = output.get(key)
                if res_id and model in self.env and self.env[model].browse(res_id).exists():
                    self.write({
                        'result_model': model,
                        'result_res_id': res_id,
                        'result_document_name': output.get(name_key) if name_key else self.env[model].browse(res_id).display_name,
                    })
                    return True
        return False

    def action_open_result_document(self):
        """Open the native document generated by the agent."""
        self.ensure_one()
        if not self.result_model or not self.result_res_id or self.result_model not in self.env:
            raise UserError(_('Esta tarea todavía no tiene un documento nativo para abrir.'))
        record = self.env[self.result_model].browse(self.result_res_id).exists()
        if not record:
            raise UserError(_('El documento nativo ya no existe.'))
        return {
            'type': 'ir.actions.act_window',
            'name': record.display_name,
            'res_model': self.result_model,
            'res_id': record.id,
            'views': [(False, 'form')],
            'target': 'new',
        }

    @api.model
    def create_from_channel(self, channel, task_type='orchestrate', prompt=False, approval_required=None, automation=False, playbook=False, source_message=False, orchestration_key=False, route=False):
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
            'source_message_id': source_message.id if source_message else False,
            'orchestration_key': orchestration_key or False,
            'orchestration_route': route or False,
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
        request_text = ' '.join([
            self.prompt or '',
            ' '.join((message.body or '') for message in self.channel_id.message_ids
                     if message.body) if self.channel_id else '',
        ]).lower()
        normalized_request = ''.join(
            char for char in unicodedata.normalize('NFKD', request_text)
            if not unicodedata.combining(char))
        quote_request = any(term in normalized_request for term in (
            'cotizacion', 'presupuesto', 'propuesta comercial',
            'pdf de la cotizacion', 'cotizacion previa'))
        meeting_request = any(term in normalized_request for term in (
            'reunion', 'videollamada', 'google meet', 'meet',
            'enlace de la reunion'))
        payment_request = any(term in request_text for term in (
            'pagar', 'pago', 'cobrar', 'link de pago', 'enlace de pago'))
        product_request = any(term in normalized_request for term in (
            'producto', 'precio', 'cuanto cuesta',
            'stock', 'disponibilidad', 'catalogo'))
        plans = {
            'classify_customer': [('classify_customer', 'Leer clasificación comercial del cliente')],
            'qualify_lead': [('classify_customer', 'Leer clasificación comercial del cliente'), ('create_lead', 'Crear o actualizar oportunidad')],
            'sales_conversion': [
                ('search_catalog', 'Buscar productos relacionados'),
                ('classify_intent', 'Identificar intención comercial'),
                ('create_lead', 'Crear oportunidad desde la conversación'),
                ('create_quotation', 'Crear cotización para el cliente'),
                ('send_quotation_pdf', 'Generar y enviar PDF de la cotización'),
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
        if self.task_type == 'orchestrate' and quote_request:
            return [
                {'key': 'search_catalog', 'name': 'Buscar productos relacionados'},
                {'key': 'create_quotation', 'name': 'Crear cotización nativa de Ventas'},
                {'key': 'send_quotation_pdf', 'name': 'Generar y enviar PDF de la cotización'},
            ]
        if self.task_type == 'orchestrate' and meeting_request:
            return [{'key': 'create_meeting', 'name': 'Crear reunión nativa y enviar enlace'}]
        if self.task_type == 'orchestrate' and payment_request:
            return [
                {'key': 'find_open_invoice', 'name': 'Consultar documento pendiente'},
                {'key': 'send_payment_link', 'name': 'Preparar link de pago'},
            ]
        if self.task_type == 'orchestrate' and product_request:
            return [
                {'key': 'search_catalog', 'name': 'Consultar catálogo vivo de Odoo'},
                {'key': 'prepare_reply', 'name': 'Preparar respuesta con datos reales'},
            ]
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
search_catalog, create_quotation, send_quotation_pdf, create_meeting, find_open_invoice,
prepare_payment_link, create_activity. No ejecutes pagos. Cotizaciones, PDFs, reuniones,
actividades y envíos requieren aprobación humana.
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
            task._sync_channel_state('awaiting_approval' if needs_approval else 'planned')
            if needs_approval:
                task._schedule_approval_activity()
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
            elif output.get('pdf_sent'):
                lines.append(_('PDF de la cotización %s enviado por Chatroom.') % output.get('order_name', _('nativa')))
            elif output.get('meeting_name'):
                sent = _('enlace enviado') if output.get('link_sent') else _('enlace preparado')
                activity = _(', actividad nativa creada') if output.get('activity_id') else ''
                lines.append(_('Reunión %s creada; %s%s.') % (output['meeting_name'], sent, activity))
            elif output.get('lines') and output.get('order_name'):
                quote_lines = '; '.join(
                    '%s x %s a %.2f %s (%.2f)' % (
                        item.get('product'), item.get('quantity'),
                        item.get('unit_price'), item.get('currency'),
                        item.get('subtotal'))
                    for item in output['lines'])
                lines.append(_(
                    'Cotización %s creada con: %s. Total: %.2f %s.'
                ) % (
                    output['order_name'], quote_lines,
                    output.get('amount_total', 0.0),
                    (output['lines'][0].get('currency') if output['lines'] else '')))
            elif output.get('order_name'):
                lines.append(_('Cotización disponible: %s.') % output['order_name'])
            elif output.get('link_id'):
                link_url = output.get('link_url')
                lines.append(_('Enlace de pago preparado: %s%s.') % (
                    output.get('document', _('documento')),
                    (' — %s' % link_url) if link_url else ''))
            elif output.get('invoices') is not None:
                lines.append(_('Facturas pendientes encontradas: %s.') % len(output['invoices']))
            elif output.get('matches') is not None:
                lines.append(_('Productos encontrados en el catálogo: %s.') % len(output['matches']))
            else:
                lines.append(_('Acción completada: %s.') % (output.get('action') or _('operación')))
        return '\n\n'.join(lines) or _('No se generó un resultado visible.')

    def _requested_meeting_window(self):
        """Interpretar una fecha/hora sencilla escrita por el cliente.

        El agente no inventa una hora: si encuentra un día de la semana y
        una hora, los convierte desde la zona horaria del usuario a UTC para
        crear un ``calendar.event`` nativo. Si faltan datos, el método deja
        que Calendario use el comportamiento seguro de una hora desde ahora.
        """
        self.ensure_one()
        request_text = ' '.join([
            self.prompt or '',
            ' '.join((message.body or '') for message in self.channel_id.message_ids
                     if message.body) if self.channel_id else '',
        ]).lower()
        time_match = re.search(
            r'\b(?:a\s+las?|para\s+las?|a\s+la|para\s+la)\s+'
            r'(\d{1,2})(?::(\d{2}))?\s*'
            r'(a\.?\s*m\.?|p\.?\s*m\.?)?\b', request_text)
        if not time_match:
            time_match = re.search(
                r'\b(\d{1,2})(?::(\d{2}))?\s*'
                r'(a\.?\s*m\.?|p\.?\s*m\.?)\b', request_text)
        if not time_match:
            return False, False
        hour = int(time_match.group(1))
        minute = int(time_match.group(2) or 0)
        meridiem = (time_match.group(3) or '').replace('.', '').replace(' ', '')
        if meridiem == 'pm' and hour < 12:
            hour += 12
        elif meridiem == 'am' and hour == 12:
            hour = 0
        if hour > 23 or minute > 59:
            return False, False

        now_utc = fields.Datetime.now()
        tz_name = self.env.user.tz or self.env.context.get('tz') or 'UTC'
        try:
            user_tz = pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            user_tz = pytz.UTC
        now_local = fields.Datetime.context_timestamp(self, now_utc)
        requested_date = now_local.date()
        if re.search(r'\b(ma[ñn]ana|pr[oó]ximo\s+d[ií]a)\b', request_text):
            requested_date += timedelta(days=1)
        else:
            weekdays = {
                'lunes': 0, 'martes': 1, 'miércoles': 2, 'miercoles': 2,
                'jueves': 3, 'viernes': 4, 'sábado': 5, 'sabado': 5,
                'domingo': 6,
            }
            weekday_match = re.search(
                r'\b(' + '|'.join(weekdays) + r')\b', request_text)
            if weekday_match:
                days_ahead = (weekdays[weekday_match.group(1)] - now_local.weekday()) % 7
                if days_ahead == 0 and 'hoy' not in request_text:
                    days_ahead = 7
                requested_date += timedelta(days=days_ahead)
        local_start = datetime.combine(requested_date, time(hour, minute))
        if local_start <= now_local.replace(tzinfo=None) and requested_date == now_local.date():
            local_start += timedelta(days=1)
        localized_start = user_tz.localize(local_start)
        start_utc = localized_start.astimezone(pytz.UTC).replace(tzinfo=None)
        stop_utc = start_utc + timedelta(hours=1)
        return fields.Datetime.to_string(start_utc), fields.Datetime.to_string(stop_utc)

    def _conversation_text(self):
        self.ensure_one()
        channel = self.channel_id
        return ' '.join([
            self.prompt or '',
            ' '.join((message.body or '') for message in channel.message_ids
                     if message.body) if channel else '',
        ]).strip()

    def _live_product_context(self):
        """Contexto compacto de productos para responder sin inventar datos."""
        self.ensure_one()
        channel = self.channel_id
        if not channel or not hasattr(channel, '_ai_search_products_mentioned'):
            return ''
        products = channel._ai_search_products_mentioned(self._conversation_text())
        lines = []
        for product in products[:8]:
            facts = channel._ai_product_commercial_data(product)
            currency = facts['currency']
            lines.append(
                '- %s | precio vigente: %.2f %s | %s' % (
                    product.display_name, facts['price'],
                    currency.symbol or currency.name, facts['stock_label']))
        return '\n'.join(lines)

    @staticmethod
    def _requested_quantity(text):
        """Read explicit hours/units from the conversation, not dates or prices."""
        patterns = (
            (r'(?<![\d.,])(\d+(?:[.,]\d+)?)\s*(?:horas?|hrs?|h)\b', 'hours'),
            (r'(?<![\d.,])(\d+(?:[.,]\d+)?)\s*(?:unidades?|uds?\.?|u)\b', 'units'),
            (r'\bx\s*(\d+(?:[.,]\d+)?)\b', 'units'),
        )
        for pattern, unit in patterns:
            match = re.search(pattern, text or '', re.IGNORECASE | re.UNICODE)
            if match:
                try:
                    value = float(match.group(1).replace(',', '.'))
                except (TypeError, ValueError):
                    continue
                if value > 0:
                    return value, unit
        return False, False

    def _requested_quote_lines(self):
        """Return the products and quantities explicitly requested by the client.

        The configured product is only a fallback. A product found in the
        live Odoo catalog always wins, which prevents a generic fixed product
        from replacing the item discussed in WhatsApp.
        """
        self.ensure_one()
        if not self.channel_id or 'product.product' not in self.env:
            return [], False, False, False
        context = self._conversation_text()
        customer_text = ' '.join(
            message.body for message in self.channel_id.message_ids
            if message.direction == 'inbound' and message.body)
        search_text = customer_text or context
        products = self.channel_id._ai_search_products_mentioned(search_text, limit=8) \
            if hasattr(self.channel_id, '_ai_search_products_mentioned') else self.env['product.product']
        if products:
            ignored = {
                'cotizacion', 'cotización', 'presupuesto', 'propuesta', 'pdf',
                'necesito', 'quiero', 'por', 'favor', 'horas', 'hora',
                'unidades', 'unidad', 'servicio', 'producto', 'productos',
                'precio', 'cantidad', 'cliente', 'para', 'con', 'una', 'uno',
            }
            def normalize(value):
                return ''.join(
                    char for char in unicodedata.normalize('NFKD', value or '').lower()
                    if not unicodedata.combining(char))

            customer_normalized = normalize(search_text)
            words = {
                normalize(word) for word in re.findall(r'\w{4,}', search_text or '', re.UNICODE)
                if word.lower() not in ignored and not word.isdigit()
            }
            scored = []
            for product in products:
                name_normalized = normalize(product.name)
                searchable = normalize(' '.join(filter(None, (
                    product.name, product.default_code, product.description_sale))))
                exact_name = name_normalized and name_normalized in customer_normalized
                score = (1000 if exact_name else 0) + sum(
                    1 for word in words
                    if word in searchable or any(
                        len(word) >= 6 and token.startswith(word[:6])
                        for token in re.findall(r'\w{4,}', searchable)))
                if score:
                    scored.append((score, product))
            exact_products = [product for score, product in scored if score >= 1000]
            if exact_products:
                products = self.env['product.product'].browse([product.id for product in exact_products])
            elif scored:
                products = self.env['product.product'].browse([max(
                    scored, key=lambda item: (item[0], -item[1].id))[1].id])
            else:
                products = self.env['product.product'].browse()
        if not products:
            configured = self.env['ir.config_parameter'].sudo().get_param(
                'chatroom_ai_agent.quote_product_id', '')
            try:
                products = self.env['product.product'].browse(int(configured)).exists() if configured else products
            except (TypeError, ValueError):
                products = self.env['product.product'].browse()
        if not products:
            return [], context, False, False
        configured_quantity = self.env['ir.config_parameter'].sudo().get_param(
            'chatroom_ai_agent.quote_quantity', '1') or '1'
        try:
            default_quantity = max(float(configured_quantity), 0.01)
        except (TypeError, ValueError):
            default_quantity = 1.0
        explicit_quantity, explicit_unit = self._requested_quantity(context)
        lines = []
        hourly_rate = self.env['ir.config_parameter'].sudo().get_param(
            'chatroom_ai_agent.quote_hourly_rate', '20') or '20'
        try:
            hourly_rate = float(hourly_rate)
        except (TypeError, ValueError):
            hourly_rate = 20.0
        for product in products[:8]:
            quantity = default_quantity
            if explicit_quantity and (explicit_unit == 'hours' or product.type != 'service'):
                quantity = explicit_quantity
            line = {'product_id': product.id, 'quantity': quantity}
            if explicit_unit == 'hours' and hourly_rate > 0:
                line['unit_price'] = hourly_rate
            lines.append(line)
        return lines, context, explicit_quantity, explicit_unit

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
                live_catalog = self._live_product_context()
                system_prompt = self.prompt or _('Prepara una respuesta breve y profesional.')
                if live_catalog:
                    system_prompt += _(
                        '\n\nDatos vivos de Odoo. Usa únicamente estos datos para '
                        'productos, precios y disponibilidad; si no aparece un '
                        'producto, dilo y pide aclaración.\n%s') % live_catalog
                result['reply'] = channel._ai_chat_completion(
                    channel._ai_build_conversation(extra_system=system_prompt),
                    task_type='reply')
            else:
                live_catalog = self._live_product_context()
                result['reply'] = (
                    _('Encontré estos datos vigentes en Odoo:\n%s') % live_catalog
                    if live_catalog else
                    _('Se preparó la tarea. Configura el proveedor de IA para generar el texto personalizado.'))
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
            if 'product.product' not in self.env:
                result['status'] = 'skipped'
                result['reason'] = _('El catálogo de productos no está disponible.')
            else:
                message_text = self._conversation_text()
                stopwords = {
                    'para', 'como', 'esta', 'este', 'cliente', 'cotización', 'cotizacion',
                    'producto', 'productos', 'quiero', 'necesito', 'desde', 'con', 'una', 'uno',
                    'del', 'por', 'que', 'los', 'las', 'una', 'sus', 'the', 'and',
                }
                terms = [term for term in re.findall(r'[\wáéíóúñü]{3,}', message_text.lower()) if term not in stopwords]
                products = self.env['product.product'].browse()
                for term in terms[:3]:
                    products |= self.env['product.product'].search([
                        ('active', '=', True), '|', ('name', 'ilike', term), ('default_code', 'ilike', term),
                    ], limit=5)
                if not products:
                    products = self.env['product.product'].search([
                        ('active', '=', True), ('sale_ok', '=', True)],
                        order='write_date desc, id desc', limit=5)
                result['matches'] = [{
                    'id': product.id,
                    'name': product.display_name,
                    'default_code': product.default_code or False,
                    'list_price': product.lst_price,
                    'price': product.lst_price,
                    'available_qty': product.free_qty if 'free_qty' in product._fields else product.qty_available if 'qty_available' in product._fields else False,
                    'type': product.type,
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
                SaleOrder = self.env['sale.order']
                order = SaleOrder.browse()
                # La clave es por tarea, no por canal. Un reintento del mismo
                # webhook reutiliza su pedido, pero una nueva solicitud del
                # cliente puede generar otra cotizaciÃ³n independiente.
                quote_marker = 'chatroom_ai_task:%s' % self.id
                if 'client_order_ref' in SaleOrder._fields:
                    order = SaleOrder.search([
                        ('client_order_ref', '=', quote_marker),
                        ('company_id', '=', self.company_id.id),
                    ], limit=1)
                if not order:
                    quote_lines, quote_context, explicit_quantity, explicit_unit = self._requested_quote_lines()
                    if quote_lines:
                        action_result = channel.action_create_quotation(product_lines=quote_lines)
                    else:
                        action_result = channel.action_create_quotation()
                        result['configuration_note'] = _(
                            'Cotización creada sin producto. Configura un producto fijo o menciona un producto vendible del catálogo de Odoo.')
                    order = SaleOrder.browse(action_result.get('res_id')).exists()
                    if order and 'client_order_ref' in order._fields:
                        order.client_order_ref = quote_marker
                if not order:
                    result['status'] = 'skipped'
                    result['reason'] = _('No se pudo crear la cotización.')
                else:
                    result.update({
                        'order_id': order.id, 'order_name': order.name,
                        'state': order.state,
                        'product': order.order_line[:1].product_id.display_name if order.order_line else False,
                        'lines': [{
                            'product': line.product_id.display_name,
                            'quantity': line.product_uom_qty,
                            'unit_price': line.price_unit,
                            'subtotal': line.price_subtotal,
                            'currency': order.currency_id.name,
                        } for line in order.order_line],
                        'amount_untaxed': order.amount_untaxed,
                        'amount_total': order.amount_total,
                        'request_context': quote_context if 'quote_context' in locals() else False,
                        'quantity_detected': explicit_quantity if 'explicit_quantity' in locals() else False,
                        'quantity_unit': explicit_unit if 'explicit_unit' in locals() else False,
                    })
        elif action.key == 'send_quotation_pdf':
            if not channel or not hasattr(channel, 'action_send_sale_order_pdf'):
                result['status'] = 'skipped'
                result['reason'] = _('El envío de PDF por Chatroom no está disponible.')
            else:
                order = self.env['sale.order'].browse()
                previous = self.action_ids.filtered(
                    lambda line: line.key == 'create_quotation' and line.state == 'done')[-1:]
                if previous and previous.output_json:
                    try:
                        previous_data = json.loads(previous.output_json)
                        order = self.env['sale.order'].browse(previous_data.get('order_id')).exists()
                    except (TypeError, ValueError, AttributeError):
                        order = self.env['sale.order'].browse()
                if not order and channel and 'sale.order' in self.env:
                    order = self.env['sale.order'].search([
                        ('partner_id', '=', partner.id),
                        ('origin', '=', channel.display_name),
                        ('state', 'in', ('draft', 'sent', 'sale')),
                        ('company_id', '=', self.company_id.id),
                    ], order='write_date desc, id desc', limit=1)
                if not order:
                    result['status'] = 'skipped'
                    result['reason'] = _('Primero se necesita una cotización nativa de Ventas.')
                else:
                    channel.action_send_sale_order_pdf(order.id)
                    result.update({
                        'order_id': order.id, 'order_name': order.name,
                        'pdf_sent': True,
                    })
        elif action.key == 'create_meeting':
            if not channel or not hasattr(channel, 'action_create_meeting'):
                result['status'] = 'skipped'
                result['reason'] = _('Instala Chatroom - Reuniones (Calendario) para crear reuniones nativas.')
            else:
                request_text = ' '.join([
                    self.prompt or '',
                    ' '.join((message.body or '') for message in channel.message_ids
                             if message.body),
                ]).strip()
                start, stop = self._requested_meeting_window()
                meeting = channel.action_create_meeting(
                    start=start, stop=stop, request=request_text)
                result.update({
                    'event_id': meeting.get('event_id'),
                    'activity_id': meeting.get('activity_id'),
                    'meeting_name': meeting.get('name') or _('Reunión'),
                    'link': meeting.get('link'),
                    'link_sent': False,
                    'start': meeting.get('start'),
                    'stop': meeting.get('stop'),
                })
                if meeting.get('link') and hasattr(channel, 'action_send_text'):
                    try:
                        channel.action_send_text(
                            _('Te comparto el enlace para la reunión: %s') % meeting['link'])
                        result['link_sent'] = True
                    except Exception as exc:  # noqa: BLE001 - conservar el evento aunque falle el canal
                        result['send_reason'] = str(exc)
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
                        'link_url': link.link if 'link' in link._fields else False,
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
            task._close_approval_activity()
            task._sync_channel_state('planned')
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
                task._sync_channel_state('done')
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
                task._close_approval_activity()
                task._store_native_result(outputs)
                task._sync_channel_state('done')
                if task.partner_id:
                    self.env['chatroom.ai.memory'].sudo().remember(task.result_summary, partner=task.partner_id, channel=task.channel_id, memory_type='outcome', source='agent')
            except Exception as exc:
                task.write({'state': 'failed', 'error_message': str(exc)})
                task._sync_channel_state('failed', reason=str(exc)[:255])
                if task.attempts >= task.max_attempts:
                    task._audit('Tarea bloqueada', 'blocked', message=_('Se alcanzó el máximo de intentos.'))
                else:
                    task._audit('Tarea fallida', 'error', message=str(exc))
                raise UserError(_('La tarea IA falló: %s') % exc)
        return True

    def action_retry(self):
        for task in self:
            task.write({
                'state': 'planned', 'error_message': False,
                'result_preview': False, 'next_run_at': fields.Datetime.now(),
            })
            task.action_ids.filtered(lambda line: line.state == 'error').write({
                'state': 'pending', 'error_message': False,
            })
            task._sync_channel_state('planned')
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

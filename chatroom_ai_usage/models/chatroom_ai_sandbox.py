# -*- coding: utf-8 -*-
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ChatroomAiSandbox(models.Model):
    _name = 'chatroom.ai.sandbox'
    _description = 'Simulador seguro de IA'
    _order = 'write_date desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Prueba', required=True, default=lambda self: _('Nueva simulación'))
    channel_id = fields.Many2one('chatroom.channel', string='Contexto de conversación')
    task_type = fields.Selection([
        ('reply', 'Respuesta'), ('summary', 'Resumen'),
        ('classification', 'Clasificación'), ('next_action', 'Próxima acción'),
        ('agent', 'Agente'),
    ], string='Tipo de tarea', default='reply', required=True)
    scenario = fields.Selection([
        ('welcome', 'Bienvenida'), ('product', 'Consulta de producto'),
        ('quote', 'Preparar cotización'), ('payment', 'Cobranza'),
        ('complaint', 'Queja o escalamiento'),
    ], string='Escenario de prueba')
    expected_keywords = fields.Char(
        string='Debe incluir',
        help='Palabras separadas por coma. La prueba las valida sin distinguir mayúsculas.')
    prompt = fields.Text(string='Instrucción', required=True)
    output = fields.Text(string='Resultado', readonly=True)
    state = fields.Selection([
        ('draft', 'Borrador'), ('done', 'Completada'), ('error', 'Error'),
    ], default='draft', required=True)
    error_message = fields.Text(string='Detalle del error', readonly=True)
    model_used = fields.Char(string='Modelo utilizado', readonly=True)
    input_tokens = fields.Integer(string='Tokens de entrada', readonly=True)
    output_tokens = fields.Integer(string='Tokens de salida', readonly=True)
    evaluation_state = fields.Selection([
        ('pending', 'Pendiente'), ('passed', 'Aprobada'),
        ('warning', 'Revisar'), ('error', 'Error'),
    ], string='Evaluación', default='pending', readonly=True)
    evaluation_note = fields.Text(string='Resultado de evaluación', readonly=True)
    delivery_state = fields.Selection([
        ('not_run', 'Sin simular'), ('simulated', 'Entrega simulada'),
    ], string='WhatsApp', default='not_run', readonly=True)
    delivery_note = fields.Text(string='Detalle de entrega', readonly=True)
    execution_mode = fields.Selection([
        ('local', 'Modo local (sin tokens)'),
        ('provider', 'Proveedor IA (consume tokens)'),
    ], string='Modo de prueba', default='local', required=True,
       help='Usa el modo local para validar el flujo sin llamadas externas. El modo proveedor consulta el modelo seleccionado.')
    provider_model_id = fields.Many2one(
        'chatroom.ai.provider.model', string='Modelo de prueba',
        domain=[('active', '=', True), ('supports_chat', '=', True)],
        help='Modelo del catálogo que se utilizará en modo proveedor.')
    draft_message = fields.Text(
        string='Mensaje del cliente',
        help='Escribe como si fueras el cliente y pulsa Enviar mensaje de prueba.')
    conversation_line_ids = fields.One2many(
        'chatroom.ai.sandbox.message', 'sandbox_id', string='Conversación de prueba',
        readonly=True)
    message_count = fields.Integer(string='Mensajes', compute='_compute_message_count')

    @api.depends('conversation_line_ids')
    def _compute_message_count(self):
        for record in self:
            record.message_count = len(record.conversation_line_ids)

    _SCENARIOS = {
        'welcome': (_('Responde una bienvenida profesional y pregunta cómo podemos ayudar.'), 'ayudar'),
        'product': (_('Explica qué productos o servicios puede consultar el cliente y ofrece revisar el catálogo.'), 'producto,catálogo'),
        'quote': (_('Prepara una respuesta para solicitar alcance, usuarios, procesos y fecha objetivo antes de cotizar.'), 'alcance,usuarios'),
        'payment': (_('Prepara un mensaje de cobranza cordial; no envíes el mensaje ni inventes un enlace.'), 'pago,enlace'),
        'complaint': (_('Identifica la queja, responde con empatía y avisa que debe revisarla un asesor humano.'), 'asesor,disculpa'),
    }

    @api.onchange('scenario')
    def _onchange_scenario(self):
        if self.scenario in self._SCENARIOS:
            prompt, keywords = self._SCENARIOS[self.scenario]
            self.prompt = prompt
            self.expected_keywords = keywords

    def action_load_scenario(self):
        self._onchange_scenario()
        return {
            'type': 'ir.actions.act_window', 'name': _('Simulador seguro de IA'),
            'res_model': self._name, 'view_mode': 'form',
            'res_id': self.id, 'target': 'current',
        }

    def _evaluate_output(self, output):
        expected = [item.strip().lower() for item in (self.expected_keywords or '').split(',') if item.strip()]
        output_lower = (output or '').lower()
        missing = [item for item in expected if item not in output_lower]
        if not expected:
            return 'pending', _('No se definieron criterios automáticos; revisa el resultado manualmente.')
        if not missing:
            return 'passed', _('La respuesta contiene todos los criterios definidos.')
        return 'warning', _('Faltan criterios: %s. Revisa la respuesta antes de usarla.') % ', '.join(missing)

    def action_simulate_delivery(self):
        for record in self:
            if record.state != 'done' or not (record.output or '').strip():
                raise UserError(_('Ejecuta primero la prueba de IA para generar un mensaje de muestra.'))
            record.write({
                'delivery_state': 'simulated',
                'delivery_note': _('Entrega simulada correctamente. No se llamó a WhatsApp y no se creó ningún mensaje real.'),
            })
        return True

    def _local_playground_reply(self, question):
        """Respuesta determinista para ensayar el chat sin consumir tokens."""
        self.ensure_one()
        normalized = re.sub(r'\s+', ' ', (question or '').strip().lower())
        normalized = re.sub(r'[^\wáéíóúñü ]', '', normalized)
        if re.fullmatch(r'(hola|buenas|buenos días|buenas tardes|buenas noches)', normalized):
            return _('Hola. Soy el asistente de prueba de Chatroom. ¿En qué podemos ayudarte?')
        if 'tarifa' in normalized or 'precio por hora' in normalized:
            knowledge_context = ''
            if 'ai.knowledge.base' in self.env:
                details = self.env['ai.knowledge.base'].sudo().get_sales_context_details(
                    channel=self.channel_id, query=question, company=self.env.company)
                # Algunas instalaciones conservan la API anterior que devuelve
                # directamente el texto, mientras que la API actual devuelve
                # un diccionario con trazabilidad. El laboratorio debe tolerar
                # ambos formatos para no bloquear una prueba local.
                knowledge_context = details.get('context') or '' if isinstance(details, dict) else (details or '')
            match = re.search(r'(?:USD|US\$)\s*\d+(?:[.,]\d+)?', knowledge_context, re.IGNORECASE)
            amount = match.group(0) if match else 'USD 20'
            return _('La tarifa referencial es %s por hora. Para preparar una cotización necesitamos alcance, usuarios, procesos y fecha objetivo.') % amount
        if any(word in normalized for word in ('producto', 'catálogo', 'catalogo', 'stock')):
            return _('Puedo consultar el catálogo de Odoo y revisar disponibilidad. Indícame el producto o servicio que necesitas.')
        if any(word in normalized for word in ('gracias', 'perfecto', 'ok')):
            return _('Con gusto. Quedamos atentos para ayudarte.')
        return _('Recibí tu consulta en el laboratorio local. En modo proveedor la IA analizaría el contexto y prepararía una respuesta basada en el conocimiento autorizado.')

    def _playground_conversation(self):
        self.ensure_one()
        system = self.prompt or _(
            'Responde en español, con tono profesional y breve. No inventes precios, stock, fechas ni enlaces. '
            'Si faltan datos o hay una queja, solicita revisión humana.')
        messages = self.channel_id._ai_build_conversation(extra_system=system)
        messages.extend({
            'role': 'user' if line.speaker == 'customer' else 'assistant',
            'content': line.body,
        } for line in self.conversation_line_ids.sorted('sequence'))
        return messages

    def action_send_test_message(self):
        """Agrega un turno cliente/IA al chat de prueba sin enviar WhatsApp."""
        self.ensure_one()
        question = (self.draft_message or '').strip()
        if not self.channel_id:
            raise UserError(_('Selecciona una conversación de referencia para probar el chat.'))
        if not question:
            raise UserError(_('Escribe el mensaje del cliente antes de enviarlo.'))
        next_sequence = max(self.conversation_line_ids.mapped('sequence') or [0]) + 1
        self.env['chatroom.ai.sandbox.message'].create({
            'sandbox_id': self.id, 'sequence': next_sequence,
            'speaker': 'customer', 'body': question,
        })
        try:
            if self.execution_mode == 'provider':
                reply = self.channel_id._ai_chat_completion(
                    self._playground_conversation(), task_type='reply',
                    model_id=self.provider_model_id.id if self.provider_model_id else None)
            else:
                reply = self._local_playground_reply(question)
            next_sequence += 1
            self.env['chatroom.ai.sandbox.message'].create({
                'sandbox_id': self.id, 'sequence': next_sequence,
                'speaker': 'assistant', 'body': reply,
            })
            values = {
                'draft_message': False, 'output': reply, 'state': 'done',
                'error_message': False, 'delivery_state': 'not_run',
                'delivery_note': _('Conversación de prueba. No se llamó a WhatsApp.'),
            }
            if self.execution_mode == 'local':
                values.update({
                    'model_used': _('Motor local'), 'input_tokens': 0,
                    'output_tokens': 0,
                    'evaluation_state': 'pending',
                    'evaluation_note': _('Respuesta local sin consumo de tokens. Revisa el contenido manualmente.'),
                })
            elif 'chatroom.ai.usage.event' in self.env:
                event = self.env['chatroom.ai.usage.event'].search([
                    ('channel_id', '=', self.channel_id.id),
                ], order='id desc', limit=1)
                if event:
                    values.update({
                        'model_used': event.model,
                        'input_tokens': event.input_tokens,
                        'output_tokens': event.output_tokens,
                    })
            self.write(values)
        except Exception as exc:
            self.write({'state': 'error', 'error_message': str(exc)})
            raise UserError(_('La respuesta de prueba falló: %s') % exc) from exc
        return {
            'type': 'ir.actions.act_window', 'name': _('Laboratorio de conversación IA'),
            'res_model': self._name, 'view_mode': 'form',
            'res_id': self.id, 'target': 'current',
        }

    def action_run(self):
        for record in self:
            if not record.channel_id:
                raise UserError(_('Selecciona una conversación para aportar contexto.'))
            try:
                messages = record.channel_id._ai_build_conversation(extra_system=record.prompt)
                result = record.channel_id._ai_chat_completion(messages, task_type=record.task_type)
                evaluation_state, evaluation_note = record._evaluate_output(result)
                record.write({
                    'output': result, 'state': 'done', 'error_message': False,
                    'evaluation_state': evaluation_state,
                    'evaluation_note': evaluation_note,
                    'delivery_state': 'not_run', 'delivery_note': False,
                })
                event = self.env['chatroom.ai.usage.event'].search([
                    ('channel_id', '=', record.channel_id.id),
                ], order='id desc', limit=1)
                if event:
                    record.write({
                        'model_used': event.model,
                        'input_tokens': event.input_tokens,
                        'output_tokens': event.output_tokens,
                    })
            except Exception as exc:
                record.write({'state': 'error', 'evaluation_state': 'error', 'error_message': str(exc)})
                raise UserError(_('La simulación falló: %s') % exc) from exc
        return True

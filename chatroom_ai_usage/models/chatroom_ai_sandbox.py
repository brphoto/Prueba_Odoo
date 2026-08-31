# -*- coding: utf-8 -*-
import base64
import re
import unicodedata

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
    ai_engine = fields.Selection([
        ('chatroom', 'Chatroom / OpenAI'),
        ('odoo_native', 'IA nativa de Odoo'),
        ('hybrid', 'Híbrida: Chatroom + Odoo'),
    ], string='Motor IA', default='chatroom', required=True,
       help='Chatroom usa el motor actual; IA nativa consulta el agente de Odoo; Híbrida usa la IA nativa como contexto y Chatroom para redactar la respuesta final.')
    engine_used = fields.Char(string='Motor utilizado', readonly=True, copy=False)
    native_engine_status = fields.Char(
        string='Estado IA nativa', compute='_compute_native_engine_status')
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
    test_quote_id = fields.Many2one(
        'sale.order', string='Cotización de prueba', readonly=True, copy=False,
        help='Presupuesto nativo generado por el laboratorio. Siempre queda en borrador.')
    quote_history_ids = fields.One2many(
        'chatroom.ai.sandbox.quote', 'sandbox_id',
        string='Historial de cotizaciones', readonly=True, copy=False)
    quote_count = fields.Integer(
        string='Cotizaciones', compute='_compute_quote_count')
    test_chat_message_id = fields.Many2one(
        'chatroom.message', string='Mensaje simulado con PDF', readonly=True, copy=False,
        help='Mensaje saliente simulado que aparece en el chat de la conversación, sin llamar a Meta.')
    test_attachment_ids = fields.Many2many(
        'ir.attachment', 'chatroom_ai_sandbox_attachment_rel', 'sandbox_id',
        'attachment_id', string='PDF y archivos generados', readonly=True, copy=False)
    test_activity_ids = fields.Many2many(
        'mail.activity', 'chatroom_ai_sandbox_activity_rel', 'sandbox_id',
        'activity_id', string='Actividades internas creadas', readonly=True, copy=False)
    test_activity_type_id = fields.Many2one(
        'mail.activity.type', string='Tipo de actividad',
        default=lambda self: (
            self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False) or
            self.env['mail.activity.type'].search([], order='sequence, id', limit=1)
        ).id,
        help='Tipo nativo que se utilizará al crear la actividad desde la prueba.')
    test_activity_user_id = fields.Many2one(
        'res.users', string='Responsable de la actividad',
        default=lambda self: self.env.user,
        help='Usuario de Odoo al que se asignará la actividad de prueba.')
    test_activity_deadline = fields.Date(
        string='Fecha límite de la actividad', default=fields.Date.context_today,
        help='Fecha límite que tendrá la actividad nativa creada en Odoo.')
    test_meeting_id = fields.Integer(
        string='ID de reunión nativa', readonly=True, copy=False,
        help='Identificador técnico del evento creado en el Calendario nativo.')
    test_meeting_name = fields.Char(
        string='Reunión creada', readonly=True, copy=False)
    test_meeting_link = fields.Char(
        string='Enlace de videollamada', readonly=True, copy=False,
        help='Enlace nativo de Odoo generado para la reunión de prueba.')
    operational_result = fields.Text(
        string='Resultado operativo de la prueba', readonly=True, copy=False,
        help='Traza de documentos y actividades creados en Odoo. No implica envío a WhatsApp.')
    knowledge_context = fields.Text(
        string='Contexto de conocimiento utilizado', readonly=True, copy=False)
    knowledge_sources = fields.Text(
        string='Fuentes de conocimiento utilizadas', readonly=True, copy=False)
    knowledge_live_sources = fields.Text(
        string='Datos vivos consultados', readonly=True, copy=False)
    knowledge_context_chars = fields.Integer(
        string='Caracteres de conocimiento', readonly=True, copy=False)
    knowledge_estimated_input_tokens = fields.Integer(
        string='Tokens estimados del conocimiento', readonly=True, copy=False)

    @api.depends('conversation_line_ids')
    def _compute_message_count(self):
        for record in self:
            record.message_count = len(record.conversation_line_ids)

    @api.depends('quote_history_ids')
    def _compute_quote_count(self):
        for record in self:
            record.quote_count = len(record.quote_history_ids)

    @api.depends('ai_engine')
    def _compute_native_engine_status(self):
        for record in self:
            if 'chatroom.ai.odoo.bridge' not in record.env:
                record.native_engine_status = _('Puente no instalado (opcional)')
                continue
            bridge = record.env['chatroom.ai.odoo.bridge'].sudo().search([
                ('company_id', '=', record.env.company.id),
            ], limit=1)
            if bridge and bridge.native_agent_id and bridge.native_agent_id.active:
                record.native_engine_status = _('Listo: %s') % bridge.native_agent_id.display_name
            else:
                record.native_engine_status = _('Requiere configurar el agente nativo')

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

    def _last_customer_request(self):
        self.ensure_one()
        customer_lines = self.conversation_line_ids.filtered(
            lambda line: line.speaker == 'customer').sorted('sequence')
        return (customer_lines[-1].body if customer_lines else self.draft_message or '').strip()

    def _quote_context(self, request=False):
        """Return the complete commercial context used by the quote test."""
        self.ensure_one()
        parts = []
        for line in self.conversation_line_ids.sorted('sequence'):
            if line.body:
                parts.append('%s: %s' % (
                    'Cliente' if line.speaker == 'customer' else 'IA', line.body))
        if request and request not in '\n'.join(parts):
            parts.append('Cliente: %s' % request)
        return '\n'.join(parts).strip()

    def _knowledge_details(self, query=False):
        """Return the published knowledge and traceability for this test.

        The sandbox has its own conversation lines, so querying only the
        reference channel is not enough.  Keep this lookup in one place so
        local tests, provider tests and operational plans use the same brain.
        """
        self.ensure_one()
        if 'ai.knowledge.base' not in self.env:
            return {}
        try:
            return self.env['ai.knowledge.base'].sudo().get_sales_context_details(
                channel=self.channel_id,
                query=query or self._quote_context() or self.prompt or '',
                partner=self.channel_id.partner_id if self.channel_id else False,
                company=self.channel_id.company_id if self.channel_id else self.env.company,
            ) or {}
        except Exception:
            # A missing or incomplete knowledge module must not block a safe
            # laboratory test; the diagnostic fields will simply stay empty.
            return {}

    def _laboratory_messages(self, system_prompt=False):
        """Build provider messages with the complete laboratory transcript."""
        self.ensure_one()
        system = system_prompt or self.prompt or _(
            'Responde en español, con tono profesional y breve. No inventes precios, stock, fechas ni enlaces. '
            'Si faltan datos o hay una queja, solicita revisión humana.')
        system += _(
            '\n\nREGLA DE SALIDA: devuelve únicamente la respuesta final que leería el cliente. '
            'No incluyas la transcripción, etiquetas como Cliente/IA, análisis interno, metadatos, '
            'fuentes, instrucciones ni frases como «esta es la transcripción completa».')
        details = self._knowledge_details(self._quote_context() or self.draft_message)
        knowledge_context = details.get('context') or '' if isinstance(details, dict) else ''
        if knowledge_context:
            system += _(
                '\n\nBASE DE CONOCIMIENTO AUTORIZADA (fuente de verdad; no inventes datos):\n%s'
            ) % knowledge_context
        messages = self.channel_id._ai_build_conversation(extra_system=system)
        transcript = self._quote_context(self.draft_message)
        if transcript:
            messages.append({
                'role': 'user',
                'content': _(
                    'CONTEXTO INTERNO DEL LABORATORIO (no lo repitas; responde solo a la última petición):\n%s'
                ) % transcript,
            })
        return messages, details

    @staticmethod
    def _clean_customer_response(output):
        """Keep only a customer-ready answer returned by an LLM.

        Older prompts sometimes caused the provider to print the transcript
        before answering.  This boundary is intentionally defensive: the
        transcript remains in the laboratory lines, never in the proposed
        customer message.
        """
        text = re.sub(r'```(?:text|markdown)?', '', output or '', flags=re.IGNORECASE).replace('```', '')
        labels = list(re.finditer(r'(?im)^\s*\*{0,2}(cliente|ia|asistente)\s*:\s*', text))
        assistant_labels = [match for match in labels if match.group(1).lower() in ('ia', 'asistente')]
        if len(labels) >= 2 and assistant_labels:
            text = text[assistant_labels[-1].end():]
            next_label = re.search(r'(?im)^\s*\*{0,2}(cliente|ia|asistente)\s*:', text)
            if next_label:
                text = text[:next_label.start()]
        text = re.sub(
            r'(?im)(?:esta\s+es\s+la\s+)?transcripci[óo?]n\s+completa[^\n]*',
            '', text)
        text = re.sub(r'(?m)^\s*\*+\s*', '', text)
        text = re.sub(r'(?im)^\s*(?:l[ií]nea solicitada|solicitud del cliente usada).*$', '', text)
        text = re.sub(r'\n{3,}', '\n\n', text).strip()
        # Internal Odoo grounding data must never leak into the customer
        # response when a provider echoes the prompt.
        clean_paragraphs = []
        for paragraph in re.split(r'\n\s*\n', text):
            normalized = ''.join(
                char for char in unicodedata.normalize('NFKD', paragraph.lower())
                if not unicodedata.combining(char))
            if any(marker in normalized for marker in (
                'linea solicitada:',
                'solicitud del cliente usada para preparar',
                'estimacion de referencia:',
                'datos comerciales verificados en odoo',
                'contexto interno del laboratorio',
            )):
                continue
            if 'precio actual de odoo' in normalized and 'producto' in normalized:
                continue
            if paragraph.strip():
                clean_paragraphs.append(paragraph.strip())
        text = '\n\n'.join(clean_paragraphs).strip()
        return text or _('No se obtuvo una respuesta utilizable. Solicita revisión humana.')

    def _native_ai_reply(self, question, details=None):
        """Ask the optional native Odoo agent without touching WhatsApp."""
        if 'chatroom.ai.odoo.bridge' not in self.env:
            raise UserError(_('Instala Chatroom - Puente IA nativa para usar este motor.'))
        bridge = self.env['chatroom.ai.odoo.bridge'].sudo().search([
            ('company_id', '=', self.env.company.id), ('active', '=', True),
        ], limit=1)
        if not bridge or not bridge.native_agent_id or not bridge.native_agent_id.active:
            raise UserError(_('Configura y activa el agente nativo de Odoo en Agente IA > Puente con Odoo.'))
        question = (question or self._last_customer_request() or self._quote_context()).strip()
        context = (details or {}).get('context', '') if isinstance(details, dict) else ''
        context_message = bridge.system_instructions or ''
        if context:
            context_message += (
                '\n\nCONTEXTO AUTORIZADO DE CHATROOM (úsalo sin repetirlo):\n%s'
            ) % context
        try:
            response = bridge.native_agent_id.get_direct_response(
                question, context_message=context_message, enable_html_response=False)
        except Exception as error:
            raise UserError(_('La IA nativa no pudo responder: %s') % error) from error
        answer = '\n\n'.join(str(item) for item in (response or []))
        return self._clean_customer_response(answer)

    def _run_ai_reply(self, question, task_type='reply'):
        """Run the selected engine and return a clean customer-ready answer."""
        self.ensure_one()
        messages, details = self._laboratory_messages(self.prompt)
        commercial_context = self._local_commercial_context(question)
        if commercial_context:
            messages[0]['content'] += (
                '\n\nDATOS COMERCIALES VERIFICADOS EN ODOO (no inventar ni repetir como transcripción): %s'
            ) % commercial_context
        if self.ai_engine in ('odoo_native', 'hybrid'):
            native_answer = self._native_ai_reply(question, details)
            if self.ai_engine == 'odoo_native':
                return native_answer, details, 'IA nativa de Odoo'
            messages[0]['content'] += (
                '\n\nRESPUESTA DE APOYO DE LA IA NATIVA (úsala como dato; redacta una única respuesta final): %s'
            ) % native_answer
        reply = self.channel_id._ai_chat_completion(
            messages, task_type=task_type,
            model_id=self.provider_model_id.id if self.provider_model_id else None)
        if task_type == 'classification':
            final_reply = reply.strip()
        else:
            final_reply = self._clean_customer_response(reply)
        return final_reply, details, (
            'Chatroom / OpenAI' if self.ai_engine == 'chatroom' else 'Híbrida: Chatroom + Odoo')

    @staticmethod
    def _quantity_from_text(text):
        """Extract an explicit commercial quantity without reading dates/prices."""
        patterns = (
            (r'(?<![\d.,])(\d+(?:[.,]\d+)?)\s*(?:horas?|hrs?|h)\b', 'hours'),
            (r'(?<![\d.,])(\d+(?:[.,]\d+)?)\s*(?:unidad(?:es)?|uds?\.?|u)\b', 'units'),
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

    def _quote_products(self, context, use_fallback=True):
        """Find mentioned products, then use the configured fallback."""
        if 'product.product' not in self.env:
            return self.env['product.product']
        products = self.env['product.product'].browse()
        customer_text = ' '.join(
            line.body for line in self.conversation_line_ids
            if line.speaker == 'customer' and line.body)
        # Prefer the request currently being quoted.  The complete transcript
        # is only a fallback for phrases such as «cotiza lo anterior».
        search_text = context or customer_text
        if self.channel_id and hasattr(self.channel_id, '_ai_search_products_mentioned'):
            # Do not let an older, similarly named product win only because it
            # appears earlier in an arbitrary limited search result.  The
            # scorer below needs the complete candidate set to honor an exact
            # product name from the current request.
            products = self.channel_id._ai_search_products_mentioned(search_text, limit=None)
        # Generic words such as "cotización" must not select an arbitrary
        # product. Keep candidates with a meaningful name/code match only.
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
        return products or (self._test_quote_product() if use_fallback else products)

    def _quote_lines_from_context(self, request=False):
        """Build quote lines from the transcript and live Odoo products."""
        self.ensure_one()
        current_request = (request or self._last_customer_request() or '').strip()
        context = self._quote_context(request) or current_request or ''
        products = self._quote_products(current_request, use_fallback=False)
        if not products:
            # If the last request uses a pronoun («lo anterior», «esas horas»)
            # resolve it against the whole laboratory transcript.
            products = self._quote_products(context)
        configured_quantity = self.env['ir.config_parameter'].sudo().get_param(
            'chatroom_ai_agent.quote_quantity', '1') or '1'
        try:
            default_quantity = max(float(configured_quantity), 0.01)
        except (TypeError, ValueError):
            default_quantity = 1.0
        explicit_quantity, explicit_unit = self._quantity_from_text(current_request)
        if not explicit_quantity:
            explicit_quantity, explicit_unit = self._quantity_from_text(context)
        lines = []
        for product in products[:8]:
            quantity = default_quantity
            if explicit_quantity and explicit_unit in ('hours', 'units'):
                quantity = explicit_quantity
            lines.append((product, quantity))
        return lines, context, explicit_quantity, explicit_unit

    def _is_quote_append_request(self, request=False):
        """Detect an explicit request to add lines to the latest draft quote."""
        self.ensure_one()
        if not self.test_quote_id or self.test_quote_id.state != 'draft':
            return False
        normalized = ''.join(
            char for char in unicodedata.normalize(
                'NFKD', request or '')
            if not unicodedata.combining(char)
        ).lower()
        phrases = (
            'agrega', 'anade', 'adiciona', 'sumale', 'incluye tambien',
            'incluye ademas', 'a la cotizacion anterior',
            'a la cotizacion actual', 'en la cotizacion actual',
            'actualiza la cotizacion', 'amplia la cotizacion',
        )
        return any(phrase in normalized for phrase in phrases)

    def _quote_unit_price(self, product, explicit_unit=False):
        """Resolve the unit price for a supervised quote.

        Normal product requests use the native Odoo price.  Hour requests use
        the configured implementation hourly rate, so a demo product priced
        at USD 1 cannot silently turn five hours into a USD 5 quotation.
        The resulting value is still written to the native sale.order.line.
        """
        if explicit_unit != 'hours':
            return product.lst_price
        raw_rate = self.env['ir.config_parameter'].sudo().get_param(
            'chatroom_ai_agent.quote_hourly_rate', '20') or '20'
        try:
            rate = float(raw_rate)
        except (TypeError, ValueError):
            rate = 20.0
        return rate if rate > 0 else product.lst_price

    def _test_quote_product(self):
        """Return the configured product used by supervised quote tests.

        The simulator follows the same product configuration as the agent. If
        it is not configured yet, it uses the first sellable product so a demo
        can be executed immediately without inventing a product in the UI.
        """
        if 'product.product' not in self.env:
            raise UserError(_('La aplicación Ventas no está instalada.'))
        icp = self.env['ir.config_parameter'].sudo()
        configured_id = icp.get_param('chatroom_ai_agent.quote_product_id')
        product = self.env['product.product'].browse(int(configured_id)).exists() if configured_id and configured_id.isdigit() else self.env['product.product']
        if not product:
            product = self.env['product.product'].search([
                ('active', '=', True), ('sale_ok', '=', True),
            ], order='id', limit=1)
        if not product:
            raise UserError(_(
                'Configura un producto de cotización o crea al menos un producto vendible para la prueba.'))
        return product[:1]

    def _create_test_quote_pdf(self, request=False, append_existing=None):
        """Create or extend a native draft quotation and attach its PDF.

        A new commercial request creates an independent ``sale.order``.  An
        explicit «agrega/añade» request extends the latest draft quotation.
        Both paths use the standard Odoo Sales report and leave a trace in the
        sandbox quote history; nothing is confirmed or sent to WhatsApp.
        """
        self.ensure_one()
        if 'sale.order' not in self.env:
            raise UserError(_('La aplicación Ventas no está instalada.'))
        if not self.channel_id or not self.channel_id.partner_id:
            raise UserError(_(
                'Vincula una conversación con un contacto antes de generar el PDF de prueba.'))
        request = (request or self._last_customer_request() or '').strip()
        append_existing = (
            self._is_quote_append_request(request)
            if append_existing is None else append_existing)
        target_order = self.test_quote_id if append_existing else self.env['sale.order']
        if append_existing and not target_order:
            append_existing = False
        if append_existing and target_order.state != 'draft':
            raise UserError(_('Solo se puede ampliar una cotización que siga en borrador.'))
        quote_lines, quote_context, explicit_quantity, explicit_unit = self._quote_lines_from_context(request)
        if not quote_lines:
            raise UserError(_('No se encontró ningún producto vendible para la cotización.'))
        order_line = []
        for product, quantity in quote_lines:
            line_values = {
                'product_id': product.id,
                'product_uom_qty': quantity,
            }
            # Las unidades de horas son una tarifa comercial configurada por
            # Chatroom. Para productos normales dejamos que Odoo resuelva el
            # precio de la lista de precios, impuestos y reglas nativas.
            if explicit_unit == 'hours':
                line_values['price_unit'] = self._quote_unit_price(product, explicit_unit)
            order_line.append((0, 0, line_values))
        before_line_ids = set(target_order.order_line.ids) if append_existing else set()
        if append_existing:
            target_order.write({'order_line': order_line})
            order = target_order
        else:
            order_values = {
                'partner_id': self.channel_id.partner_id.id,
                'origin': _('Laboratorio IA: %s') % self.name,
                'client_order_ref': _('Prueba supervisada; no enviar automáticamente'),
                'order_line': order_line,
            }
            order = self.env['sale.order'].create(order_values)
        report_xmlid = 'sale.action_report_saleorder'
        report = self.env.ref(report_xmlid, raise_if_not_found=False)
        if not report:
            raise UserError(_('No está instalado el reporte estándar de presupuestos de Ventas.'))
        try:
            pdf_content, _report_type = self.env['ir.actions.report'].with_context(
                force_report_rendering=True)._render_qweb_pdf(report_xmlid, res_ids=[order.id])
        except Exception as exc:
            if not append_existing:
                order.unlink()
            raise UserError(_('No se pudo generar el PDF estándar de Ventas: %s') % exc) from exc
        if not pdf_content:
            if not append_existing:
                order.unlink()
            raise UserError(_('El reporte estándar no devolvió contenido PDF.'))
        attachment = self.env['ir.attachment'].create({
            'name': _('%s - Cotización de prueba.pdf') % order.name,
            'type': 'binary',
            'datas': base64.b64encode(pdf_content),
            'res_model': 'sale.order',
            'res_id': order.id,
            'mimetype': 'application/pdf',
        })
        simulated_message = self.env['chatroom.message'].create({
            'channel_id': self.channel_id.id,
            'direction': 'outbound',
            'message_type': 'document',
            'body': _(
                'Prueba IA: cotización %s generada. PDF adjunto; no se envió a WhatsApp. %s'
            ) % (order.name, self._local_commercial_context(request)),
            'state': 'sent',
            'date': fields.Datetime.now(),
            'attachment_ids': [(4, attachment.id)],
            'sender_user_id': self.env.user.id,
        })
        # This is an internal laboratory notification. Keep it concise: the
        # detailed lines and the original request remain in the sandbox and
        # quote history, not in a message that can be mistaken for a reply.
        simulated_message.write({
            'body': _(
                'Prueba IA: cotización %s generada en borrador. PDF adjunto; '
                'no se envió a WhatsApp.'
            ) % order.name,
        })
        order.message_post(
            body=_('PDF de cotización generado desde una prueba de IA. El presupuesto permanece en borrador.'),
            attachment_ids=[attachment.id],
            subtype_xmlid='mail.mt_note',
        )
        generated_lines = order.order_line.filtered(
            lambda line: line.id not in before_line_ids) if append_existing else order.order_line
        line_summary = ', '.join(
            '%s x %s (%.2f %s c/u)' % (
                line.product_id.display_name, line.product_uom_qty, line.price_unit,
                order.currency_id.symbol or order.currency_id.name)
            for line in generated_lines
        )
        quantity_note = (
            _(' Cantidad detectada: %s %s.') % (
                explicit_quantity, 'hora(s)' if explicit_unit == 'hours' else 'unidad(es)')
            if explicit_quantity else '')
        operation_label = _('ampliada') if append_existing else _('creada')
        note = _(
            'Cotización %s %s en borrador con estas líneas: %s.%s PDF adjunto al presupuesto y a esta prueba. '
            'No se confirmó ni se envió ningún mensaje.'
        ) % (order.name, operation_label, line_summary, quantity_note)
        history = self.env['chatroom.ai.sandbox.quote'].create({
            'sandbox_id': self.id,
            'operation': 'append' if append_existing else 'new',
            'request_text': request,
            'sale_order_id': order.id,
            'attachment_id': attachment.id,
            'chat_message_id': simulated_message.id,
            'product_summary': line_summary,
            'detected_quantity': explicit_quantity or 0.0,
            'amount_untaxed': order.amount_untaxed,
            'amount_total': order.amount_total,
            'currency_id': order.currency_id.id,
        })
        self.write({
            'test_quote_id': order.id,
            'test_chat_message_id': simulated_message.id,
            'test_attachment_ids': [(4, attachment.id)],
            'operational_result': note,
        })
        self.message_post(body=note, attachment_ids=[attachment.id], subtype_xmlid='mail.mt_note')
        return order, attachment, simulated_message, history

    def action_generate_test_quote_pdf(self):
        """Button for an explicit, visible quote/PDF test."""
        self.ensure_one()
        self._create_test_quote_pdf(self._last_customer_request())
        return {
            'type': 'ir.actions.act_window', 'name': _('Prueba IA'),
            'res_model': self._name, 'res_id': self.id,
            'view_mode': 'form', 'target': 'current',
        }

    def _create_test_activity(self, request=False):
        """Create a real internal Odoo activity without external delivery."""
        self.ensure_one()
        if 'mail.activity' not in self.env:
            raise UserError(_('La aplicación Discusiones no está instalada.'))
        target = self.channel_id or (self.channel_id.partner_id if self.channel_id else False)
        if not target:
            raise UserError(_('Vincula una conversación antes de crear una actividad interna.'))
        model_name = target._name
        model = self.env['ir.model']._get(model_name)
        activity_type = self.test_activity_type_id or self.env.ref(
            'mail.mail_activity_data_todo', raise_if_not_found=False)
        activity_type = activity_type or self.env['mail.activity.type'].search(
            [], order='sequence, id', limit=1)
        if not activity_type:
            raise UserError(_('No existe ningún tipo de actividad en Odoo.'))
        request = (request or self._last_customer_request() or self.prompt or '').strip()
        activity = self.env['mail.activity'].create({
            'activity_type_id': activity_type.id,
            'res_model_id': model.id,
            'res_id': target.id,
            'user_id': (self.test_activity_user_id or self.env.user).id,
            'date_deadline': self.test_activity_deadline or fields.Date.context_today(self),
            'summary': _('Revisar solicitud del laboratorio IA'),
            'note': _('Solicitud de prueba: %s') % request,
        })
        note = _(
            'Actividad interna creada en %s para %s: «%s». La actividad queda en Odoo para seguimiento; '
            'no se envió WhatsApp.'
        ) % (target.display_name, self.env.user.display_name, activity.summary)
        self.write({
            'test_activity_ids': [(4, activity.id)],
            'operational_result': '%s\n%s' % ((self.operational_result or '').strip(), note),
        })
        self.message_post(body=note, subtype_xmlid='mail.mt_note')
        return activity

    def action_create_test_activity(self):
        """Button for an explicit native mail.activity test."""
        self.ensure_one()
        self._create_test_activity(self._last_customer_request())
        return {
            'type': 'ir.actions.act_window', 'name': _('Prueba IA'),
            'res_model': self._name, 'res_id': self.id,
            'view_mode': 'form', 'target': 'current',
        }

    def _create_test_meeting(self, request=False):
        """Create and record a native Calendar meeting without external delivery."""
        self.ensure_one()
        channel = self.channel_id
        if not channel or not channel.partner_id:
            raise UserError(_('Vincula una conversación con un contacto antes de crear la reunión.'))
        if not hasattr(channel, 'action_create_meeting'):
            raise UserError(_(
                'Instala el módulo Chatroom - Calendario para usar la agenda nativa y la videollamada de Odoo.'))
        meeting = channel.action_create_meeting(request=request or self._last_customer_request())
        note = _(
            'Reunión nativa creada en Calendario para %s. Enlace generado: %s. '
            'La prueba no envió ningún mensaje externo.'
        ) % (channel.partner_id.display_name, meeting.get('link'))
        values = {
            'test_meeting_id': meeting.get('event_id') or 0,
            'test_meeting_name': meeting.get('name') or False,
            'test_meeting_link': meeting.get('link') or False,
            'operational_result': '%s\n%s' % ((self.operational_result or '').strip(), note),
        }
        if meeting.get('activity_id'):
            values['test_activity_ids'] = [(4, meeting['activity_id'])]
        self.write(values)
        self.message_post(body=note, subtype_xmlid='mail.mt_note')
        return meeting

    def action_create_test_meeting(self):
        """Create a native Odoo Calendar meeting without external delivery."""
        self.ensure_one()
        self._create_test_meeting(self._last_customer_request())
        return {
            'type': 'ir.actions.act_window', 'name': _('Prueba IA'),
            'res_model': self._name, 'res_id': self.id,
            'view_mode': 'form', 'target': 'current',
        }

    def _process_test_operations(self, request):
        """Materialize safe Odoo artifacts requested in a test conversation."""
        self.ensure_one()
        normalized = (request or '').lower()
        notes = []
        if any(word in normalized for word in ('cotización', 'cotizacion', 'presupuesto', 'pdf')):
            try:
                order, attachment, simulated_message, history = self._create_test_quote_pdf(request)
                operation_label = (
                    _('ampliada') if history.operation == 'append' else _('creada'))
                notes.append(_(
                    'PDF listo: %s (presupuesto %s %s). También se agregó al chat como mensaje simulado (%s).'
                ) % (attachment.name, order.name, operation_label, simulated_message.display_name))
            except UserError as exc:
                notes.append(_('No se pudo generar el PDF de prueba: %s') % exc)
        if any(word in normalized for word in ('actividad', 'tarea interna', 'llamada', 'seguimiento')) and not self.test_activity_ids:
            try:
                activity = self._create_test_activity(request)
                notes.append(_('Actividad interna creada para %s.') % activity.date_deadline)
            except UserError as exc:
                notes.append(_('No se pudo crear la actividad interna: %s') % exc)
        if any(word in normalized for word in (
            'reunión', 'reunion', 'videollamada', 'google meet',
            'enlace de reunión', 'enlace de reunion', 'agendar', 'cita')):
            if self.test_meeting_id:
                return '\n'.join(notes)
            try:
                meeting = self._create_test_meeting(request)
                notes.append(_(
                    'Reunión nativa creada en Calendario: %s. Enlace: %s.'
                ) % (meeting.get('name') or _('Reunión'), meeting.get('link') or _('no disponible')))
            except UserError as exc:
                notes.append(_('No se pudo crear la reunión nativa: %s') % exc)
        if notes:
            self.write({'operational_result': '%s\n%s' % (
                (self.operational_result or '').strip(), '\n'.join(notes))})
        return '\n'.join(notes)

    def _local_playground_reply(self, question):
        """Respuesta determinista para ensayar el chat sin consumir tokens."""
        self.ensure_one()
        normalized = re.sub(r'\s+', ' ', (question or '').strip().lower())
        normalized = re.sub(r'[^\wáéíóúñü ]', '', normalized)
        if re.fullmatch(r'(hola|buenas|buenos días|buenas tardes|buenas noches)', normalized):
            return _('Hola. Soy el asistente de prueba de Chatroom. ¿En qué podemos ayudarte?')
        if 'tarifa' in normalized or 'precio por hora' in normalized:
            details = self._knowledge_details(question)
            knowledge_context = details.get('context') or '' if isinstance(details, dict) else ''
            amounts = self._maximum_amounts_from_context(knowledge_context)
            amount = 'USD %.2f' % max(amounts) if amounts else 'USD 20'
            return _(
                'La tarifa referencial es %s por hora. Para preparar una cotización necesitamos alcance, usuarios, procesos y fecha objetivo.'
            ) % amount
        if any(word in normalized for word in (
            'cotización', 'cotizacion', 'presupuesto', 'pdf',
            'pdf de la cotización', 'pdf de la cotizacion')):
            commercial_context = self._local_commercial_context(question)
            response = _(
                'Puedo preparar una cotización nativa de Ventas con el producto configurado, generar su PDF y dejarlo listo para enviarlo por Chatroom. La creación y el envío requieren aprobación humana.'
            )
            return '%s\n\n%s' % (response, commercial_context) if commercial_context else response
        if any(word in normalized for word in ('reunión', 'reunion', 'videollamada', 'google meet', 'enlace de reunión', 'enlace de reunion')):
            return _('Puedo crear una reunión nativa en Calendario con un enlace de videollamada y compartirlo por Chatroom. La acción queda preparada para aprobación humana.')
        if any(word in normalized for word in ('producto', 'catálogo', 'catalogo', 'stock')):
            commercial_context = self._local_commercial_context(question)
            response = _('Puedo consultar el catálogo vivo de Odoo y revisar disponibilidad.')
            return '%s\n\n%s' % (response, commercial_context) if commercial_context else response
        if any(word in normalized for word in ('gracias', 'perfecto', 'ok')):
            return _('Con gusto. Quedamos atentos para ayudarte.')
        details = self._knowledge_details(question)
        knowledge_context = details.get('context') or '' if isinstance(details, dict) else ''
        if knowledge_context:
            sources = details.get('sources') or [] if isinstance(details, dict) else []
            source_text = ', '.join(item.get('name') for item in sources if item.get('name'))
            trace = _('Fuente utilizada: %s.') % source_text if source_text else ''
            return _('Con base en el conocimiento autorizado de Odoo:\n\n%s\n\n%s') % (
                knowledge_context[:1800], trace)
        return _('Recibí tu consulta en el laboratorio local. En modo proveedor la IA analizaría el contexto y prepararía una respuesta basada en el conocimiento autorizado.')

    @staticmethod
    def _maximum_amounts_from_context(context):
        """Extract monetary values and use the upper end of any range.

        Company knowledge often says “USD 200 a USD 300”. The assistant must
        not answer with the lower number, so all values are normalized and the
        maximum is used for the safe local estimate.
        """
        number = r'(\d+(?:[.,]\d+)?)'
        range_pattern = re.compile(
            r'(?:USD|US\$|\$)\s*' + number +
            r'\s*(?:a|al|hasta|y|[-–—])\s*(?:(?:USD|US\$|\$)\s*)?' + number,
            re.IGNORECASE,
        )
        values = []
        for match in range_pattern.finditer(context or ''):
            values.extend(match.groups())
        singles = re.findall(r'(?:USD|US\$|\$)\s*' + number, context or '', re.IGNORECASE)
        values.extend(singles)
        normalized = []
        for value in values:
            try:
                normalized.append(float(value.replace(',', '.')))
            except (TypeError, ValueError):
                continue
        return normalized

    def _local_commercial_context(self, question):
        """Return live quote lines and the upper bound of knowledge ranges."""
        self.ensure_one()
        lines = []
        normalized_question = (question or '').lower()
        is_quote_request = any(word in normalized_question for word in (
            'cotización', 'cotizacion', 'presupuesto', 'pdf'))
        quote_context = ''
        if is_quote_request:
            try:
                quote_lines, quote_context, _quantity, _unit = self._quote_lines_from_context(question)
            except UserError:
                quote_lines, quote_context = [], question or ''
            for product, quantity in quote_lines:
                facts = self.channel_id._ai_product_commercial_data(product, quantity=quantity)
                currency = facts['currency']
                price = self._quote_unit_price(product, _unit if is_quote_request else False)
                amount = price * quantity
                lines.append(_(
                    'Línea solicitada: %(product)s | cantidad %(quantity)s | '
                    'precio actual de Odoo %(price).2f %(currency)s | '
                    'importe %(amount).2f %(currency)s (%(stock)s).'
                ) % {
                    'product': product.display_name,
                    'quantity': quantity,
                    'price': price,
                    'currency': currency.symbol or currency.name,
                    'amount': amount,
                    'stock': facts['stock_label'],
                })
            products = self.env['product.product'].browse([
                product.id for product, _quantity in quote_lines])
        elif self.channel_id and hasattr(self.channel_id, '_ai_search_products_mentioned'):
            products = self.channel_id._ai_search_products_mentioned(question, limit=5)
        else:
            products = self.env['product.product']
        if not products and self.channel_id and hasattr(self.channel_id, '_ai_search_products_mentioned'):
            products = self.channel_id._ai_search_products_mentioned(question, limit=5)
        if not is_quote_request and products:
            for product in products:
                facts = self.channel_id._ai_product_commercial_data(product)
                currency = facts['currency']
                lines.append(_(
                    'Producto «%(product)s»: precio actual de Odoo %(price).2f %(currency)s (%(stock)s).'
                ) % {
                    'product': product.display_name,
                    'price': facts['price'],
                    'currency': currency.symbol or currency.name,
                    'stock': facts['stock_label'],
                })
        if is_quote_request and quote_context:
            customer_context = ' '.join(
                line.body for line in self.conversation_line_ids
                if line.speaker == 'customer' and line.body)
            lines.append(_('Solicitud del cliente usada para preparar la cotización: %s') % re.sub(
                r'\s+', ' ', customer_context or question or '').strip()[:500])
        details = self._knowledge_details(question)
        if details:
            knowledge_context = details.get('context') or '' if isinstance(details, dict) else ''
            amounts = self._maximum_amounts_from_context(knowledge_context)
            if amounts:
                lines.append(_(
                    'Estimación de referencia: %(amount)s (se usa el límite superior cuando el conocimiento contiene un rango).'
                ) % {'amount': 'USD %.2f' % max(amounts)})
        return ' '.join(lines)

    def action_prepare_operational_task(self):
        """Convierte la última petición del laboratorio en un plan real.

        El laboratorio nunca ejecuta la operación ni envía por WhatsApp: solo
        crea la tarea del agente para que el usuario pueda revisar, aprobar y
        ejecutar la cotización/PDF o la reunión desde el flujo normal.
        """
        self.ensure_one()
        if 'chatroom.ai.task' not in self.env:
            raise UserError(_('Instala Chatroom Agente IA para preparar acciones operativas.'))
        customer_lines = self.conversation_line_ids.filtered(
            lambda line: line.speaker == 'customer').sorted('sequence')
        request = (customer_lines[-1].body if customer_lines else self.draft_message or '').strip()
        if not request:
            raise UserError(_('Escribe primero una petición del cliente en el chat de prueba.'))
        transcript = self._quote_context(request)
        task = self.env['chatroom.ai.task'].create_from_channel(
            self.channel_id, task_type='orchestrate',
            prompt=_('Petición del laboratorio:\n%s\n\nTranscripción completa:\n%s') % (
                request, transcript),
            approval_required=True)
        task.action_plan()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Plan operativo IA'),
            'res_model': 'chatroom.ai.task',
            'res_id': task.id,
            'views': [(False, 'form')],
            'target': 'new',
        }

    def _playground_conversation(self):
        self.ensure_one()
        messages, _details = self._laboratory_messages(self.prompt)
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
                reply, knowledge_details, engine_used = self._run_ai_reply(question, task_type='reply')
            else:
                reply = self._clean_customer_response(
                    self._local_playground_reply(question))
                knowledge_details = self._knowledge_details(self._quote_context(question))
                engine_used = _('Motor local')
            next_sequence += 1
            assistant_line = self.env['chatroom.ai.sandbox.message'].create({
                'sandbox_id': self.id, 'sequence': next_sequence,
                'speaker': 'assistant', 'body': reply,
            })
            values = {
                'draft_message': False, 'output': reply, 'state': 'done',
                'error_message': False, 'delivery_state': 'not_run',
                'delivery_note': _('Conversación de prueba. No se llamó a WhatsApp.'),
                'knowledge_context': knowledge_details.get('context') or '',
                'knowledge_sources': '\n'.join(
                    '- %s (v%s)' % (item.get('name') or _('Fuente'), item.get('version', 1))
                    for item in (knowledge_details.get('sources') or []) if item.get('name')),
                'knowledge_live_sources': '\n'.join(
                    '- %s' % item for item in (knowledge_details.get('live_sources') or []) if item),
                'knowledge_context_chars': knowledge_details.get('context_chars', 0),
                'knowledge_estimated_input_tokens': knowledge_details.get('estimated_input_tokens', 0),
                'engine_used': engine_used,
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
            operation_note = self._process_test_operations(question)
            # Una reunión creada en Calendario sí debe ser visible y utilizable
            # desde el chat simulado. Las notas internas permanecen en el
            # resultado operativo; solo exponemos el enlace al cliente.
            if self.test_meeting_link and self.test_meeting_link not in (assistant_line.body or ''):
                assistant_line.write({
                    'body': '%s\n\nEnlace de reunión: %s' % (
                        assistant_line.body or '', self.test_meeting_link),
                })
            # El PDF también queda en el turno de IA del laboratorio, no
            # únicamente en el chatter de la prueba o del presupuesto.
            if self.test_chat_message_id and self.test_chat_message_id.attachment_ids:
                values = {'attachment_ids': [(4, self.test_chat_message_id.attachment_ids[0].id)]}
                assistant_line.write(values)
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
                if record.execution_mode == 'provider':
                    result, details, engine_used = record._run_ai_reply(
                        record._last_customer_request() or record.draft_message,
                        task_type=record.task_type)
                else:
                    details = record._knowledge_details(record._quote_context(record.draft_message))
                    result = record._clean_customer_response(
                        record._local_playground_reply(
                            record._last_customer_request() or record.draft_message))
                    engine_used = _('Motor local')
                evaluation_state, evaluation_note = record._evaluate_output(result)
                record.write({
                    'output': result, 'state': 'done', 'error_message': False,
                    'evaluation_state': evaluation_state,
                    'evaluation_note': evaluation_note,
                    'delivery_state': 'not_run', 'delivery_note': False,
                    'knowledge_context': details.get('context') or '',
                    'knowledge_sources': '\n'.join(
                        '- %s (v%s)' % (item.get('name') or _('Fuente'), item.get('version', 1))
                        for item in (details.get('sources') or []) if item.get('name')),
                    'knowledge_live_sources': '\n'.join(
                        '- %s' % item for item in (details.get('live_sources') or []) if item),
                    'knowledge_context_chars': details.get('context_chars', 0),
                    'knowledge_estimated_input_tokens': details.get('estimated_input_tokens', 0),
                    'engine_used': engine_used,
                    'operational_result': _(
                        'El análisis utilizó la conversación completa del laboratorio y la base de conocimiento publicada. '
                        'Fuentes: %s. Datos vivos: %s.'
                    ) % (
                        ', '.join(item.get('name') for item in (details.get('sources') or []) if item.get('name')) or _('ninguna'),
                        ', '.join(details.get('live_sources') or []) or _('ninguno'),
                    ),
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
                # "No enviar" means no external WhatsApp delivery, not that
                # the laboratory ignores an explicit native Odoo operation.
                # Use the complete transcript so a follow-up such as
                # "envíame aquí" still preserves the earlier meeting/quote
                # request. The idempotence guards above prevent duplicates.
                operation_request = record._quote_context(record.draft_message)
                operation_note = record._process_test_operations(operation_request)
                if operation_note:
                    record.write({
                        'operational_result': '%s\n%s' % (
                            (record.operational_result or '').strip(),
                            _('El laboratorio materializó operaciones nativas sin enviar a WhatsApp:\n%s') % operation_note,
                        ),
                    })
            except Exception as exc:
                record.write({'state': 'error', 'evaluation_state': 'error', 'error_message': str(exc)})
                raise UserError(_('La simulación falló: %s') % exc) from exc
        return True

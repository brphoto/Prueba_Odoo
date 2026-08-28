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
                'content': _('Transcripción completa del laboratorio:\n%s') % transcript,
            })
        return messages, details

    @staticmethod
    def _quantity_from_text(text):
        """Extract an explicit commercial quantity without reading dates/prices."""
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

    def _quote_products(self, context):
        """Find mentioned products, then use the configured fallback."""
        if 'product.product' not in self.env:
            return self.env['product.product']
        products = self.env['product.product'].browse()
        customer_text = ' '.join(
            line.body for line in self.conversation_line_ids
            if line.speaker == 'customer' and line.body)
        search_text = customer_text or context
        if self.channel_id and hasattr(self.channel_id, '_ai_search_products_mentioned'):
            products = self.channel_id._ai_search_products_mentioned(search_text, limit=8)
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
        return products or self._test_quote_product()

    def _quote_lines_from_context(self, request=False):
        """Build quote lines from the transcript and live Odoo products."""
        self.ensure_one()
        context = self._quote_context(request) or request or ''
        products = self._quote_products(context)
        configured_quantity = self.env['ir.config_parameter'].sudo().get_param(
            'chatroom_ai_agent.quote_quantity', '1') or '1'
        try:
            default_quantity = max(float(configured_quantity), 0.01)
        except (TypeError, ValueError):
            default_quantity = 1.0
        explicit_quantity, explicit_unit = self._quantity_from_text(context)
        lines = []
        for product in products[:8]:
            quantity = default_quantity
            if explicit_quantity and (explicit_unit == 'hours' or product.type != 'service'):
                quantity = explicit_quantity
            lines.append((product, quantity))
        return lines, context, explicit_quantity, explicit_unit

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

    def _create_test_quote_pdf(self, request=False):
        """Create a native draft quotation and attach its standard PDF.

        This is deliberately a sandbox operation: no confirmation, invoice,
        payment or WhatsApp message is performed. The PDF is linked to the
        quotation and to the sandbox so it is visible from both records.
        """
        self.ensure_one()
        if 'sale.order' not in self.env:
            raise UserError(_('La aplicación Ventas no está instalada.'))
        if not self.channel_id or not self.channel_id.partner_id:
            raise UserError(_(
                'Vincula una conversación con un contacto antes de generar el PDF de prueba.'))
        quote_lines, quote_context, explicit_quantity, explicit_unit = self._quote_lines_from_context(request)
        if not quote_lines:
            raise UserError(_('No se encontró ningún producto vendible para la cotización.'))
        order_line = [(0, 0, {
            'product_id': product.id,
            'product_uom_qty': quantity,
        }) for product, quantity in quote_lines]
        request_ref = re.sub(r'\s+', ' ', quote_context or request or '').strip()[:180]
        order_values = {
            'partner_id': self.channel_id.partner_id.id,
            'origin': _('Laboratorio IA: %s') % self.name,
            'client_order_ref': _('Prueba supervisada; no enviar automáticamente'),
            'order_line': order_line,
        }
        if 'note' in self.env['sale.order']._fields:
            order_values['note'] = _('Solicitud del cliente (laboratorio IA):\n%s') % request_ref
        order = self.env['sale.order'].create(order_values)
        report_xmlid = 'sale.action_report_saleorder'
        report = self.env.ref(report_xmlid, raise_if_not_found=False)
        if not report:
            raise UserError(_('No está instalado el reporte estándar de presupuestos de Ventas.'))
        try:
            pdf_content, _report_type = self.env['ir.actions.report'].with_context(
                force_report_rendering=True)._render_qweb_pdf(report_xmlid, res_ids=[order.id])
        except Exception as exc:
            order.unlink()
            raise UserError(_('No se pudo generar el PDF estándar de Ventas: %s') % exc) from exc
        if not pdf_content:
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
        order.message_post(
            body=_('PDF de cotización generado desde una prueba de IA. El presupuesto permanece en borrador.'),
            attachment_ids=[attachment.id],
            subtype_xmlid='mail.mt_note',
        )
        line_summary = ', '.join(
            '%s x %s (%.2f %s c/u)' % (
                product.display_name, quantity, line.price_unit,
                order.currency_id.symbol or order.currency_id.name)
            for line, (product, quantity) in zip(order.order_line, quote_lines)
        )
        quantity_note = (
            _(' Cantidad detectada: %s %s.') % (
                explicit_quantity, 'hora(s)' if explicit_unit == 'hours' else 'unidad(es)')
            if explicit_quantity else '')
        note = _(
            'Cotización %s creada en borrador con estas líneas: %s.%s PDF adjunto al presupuesto y a esta prueba. '
            'No se confirmó ni se envió ningún mensaje.'
        ) % (order.name, line_summary, quantity_note)
        self.write({
            'test_quote_id': order.id,
            'test_chat_message_id': simulated_message.id,
            'test_attachment_ids': [(4, attachment.id)],
            'operational_result': note,
        })
        self.message_post(body=note, attachment_ids=[attachment.id], subtype_xmlid='mail.mt_note')
        return order, attachment, simulated_message

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
        if any(word in normalized for word in ('cotización', 'cotizacion', 'presupuesto', 'pdf')) and not self.test_quote_id:
            try:
                order, attachment, simulated_message = self._create_test_quote_pdf(request)
                notes.append(_(
                    'PDF listo: %s (presupuesto %s). También se agregó al chat como mensaje simulado (%s).'
                ) % (attachment.name, order.name, simulated_message.display_name))
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
                amount = facts['price'] * quantity
                lines.append(_(
                    'Línea solicitada: %(product)s | cantidad %(quantity)s | '
                    'precio actual de Odoo %(price).2f %(currency)s | '
                    'importe %(amount).2f %(currency)s (%(stock)s).'
                ) % {
                    'product': product.display_name,
                    'quantity': quantity,
                    'price': facts['price'],
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
            knowledge_details = self._knowledge_details(self._quote_context(question))
            if self.execution_mode == 'provider':
                playground_messages = self._playground_conversation()
                commercial_context = self._local_commercial_context(question)
                if commercial_context:
                    playground_messages[0]['content'] += _(
                        '\n\nContexto comercial verificado por Odoo (úsalo como fuente de verdad): %s'
                    ) % commercial_context
                reply = self.channel_id._ai_chat_completion(
                    playground_messages, task_type='reply',
                    model_id=self.provider_model_id.id if self.provider_model_id else None)
            else:
                reply = self._local_playground_reply(question)
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
            if operation_note and operation_note not in (reply or ''):
                assistant_line.write({'body': '%s\n\n%s' % (reply, operation_note)})
            # El PDF también queda en el turno de IA del laboratorio, no
            # únicamente en el chatter de la prueba o del presupuesto.
            if self.test_chat_message_id and self.test_chat_message_id.attachment_ids:
                commercial_context = self._local_commercial_context(question)
                values = {'attachment_ids': [(4, self.test_chat_message_id.attachment_ids[0].id)]}
                if commercial_context and commercial_context not in (reply or ''):
                    values['body'] = '%s\n\n%s' % (reply, commercial_context)
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
                messages, details = record._laboratory_messages(record.prompt)
                result = record.channel_id._ai_chat_completion(messages, task_type=record.task_type)
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

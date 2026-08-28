# -*- coding: utf-8 -*-
import base64
import hashlib
import io
import logging
import re
from datetime import timedelta

from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class AiKnowledgeBase(models.Model):
    _name = 'ai.knowledge.base'
    _description = 'Manual interno para asistencia IA'
    _order = 'name'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', string='Empresa', default=lambda self: self.env.company,
        index=True, help='Vacío significa disponible para todas las empresas.')
    source_type = fields.Selection([
        ('text', 'Texto interno'),
        ('pdf', 'Documento PDF'),
    ], string='Tipo de conocimiento', default='text', required=True)
    publication_state = fields.Selection([
        ('published', 'Publicado'), ('draft', 'Borrador'),
        ('archived', 'Archivado'),
    ], string='Disponibilidad para la IA', default='published', required=True,
        help='Solo el conocimiento publicado se recupera en las respuestas de IA.')
    published_at = fields.Datetime(string='Publicado el', readonly=True)
    category = fields.Selection([
        ('general', 'General'),
        ('products', 'Productos y servicios'),
        ('sales', 'Ventas'),
        ('support', 'Soporte'),
        ('payments', 'Pagos y facturación'),
        ('policies', 'Políticas y condiciones'),
    ], string='Categoría', default='general', required=True)
    priority = fields.Integer(string='Prioridad', default=10)
    source_text = fields.Text(
        string='Contenido interno',
        help='Escribe aquí políticas, preguntas frecuentes, procesos y datos '
             'que no viven en una tabla de Odoo. La IA usará este contenido '
             'después de indexarlo.')
    knowledge_format = fields.Selection([
        ('natural', 'Texto natural'), ('faq', 'Preguntas frecuentes'),
        ('policy', 'Política o regla'), ('product', 'Producto o servicio'),
        ('playbook', 'Procedimiento comercial'),
    ], string='Cómo organizarlo', default='natural', required=True,
        help='Ayuda a ordenar el contenido para que la IA encuentre respuestas y reglas sin escribir código.')
    organization_state = fields.Selection([
        ('raw', 'Sin organizar'), ('organized', 'Organizado localmente'),
    ], string='Organización', default='raw', readonly=True)
    organized_summary = fields.Text(string='Resumen organizado', readonly=True)
    key_points = fields.Text(string='Puntos clave', readonly=True)
    faq_entries = fields.Text(string='Preguntas y respuestas detectadas', readonly=True)
    operational_rules = fields.Text(string='Reglas operativas detectadas', readonly=True)
    organized_text = fields.Text(string='Contenido estructurado para la IA', readonly=True)
    organization_notes = fields.Text(string='Notas de organización', readonly=True)
    pdf_file = fields.Binary(string='Manual PDF', attachment=True)
    pdf_filename = fields.Char(string='Nombre del archivo')
    ocr_status = fields.Selection([
        ('not_needed', 'No necesario'), ('required', 'Requiere OCR'),
        ('processed', 'OCR procesado'), ('unavailable', 'OCR no disponible'),
    ], string='OCR', default='not_needed', readonly=True)
    ocr_text = fields.Text(string='Texto obtenido por OCR', readonly=True)
    content_text = fields.Text(string='Texto indexado', readonly=True)
    chunk_count = fields.Integer(readonly=True)
    state = fields.Selection([
        ('pending', 'Pendiente'), ('indexed', 'Indexado'), ('error', 'Error'),
    ], default='pending', readonly=True)
    processing_error = fields.Text(readonly=True)
    keyword_tags = fields.Char(string='Palabras clave', help='Términos separados por coma para priorizar este manual.')
    indexed_at = fields.Datetime(string='Indexado el', readonly=True)
    owner_id = fields.Many2one(
        'res.users', string='Responsable', default=lambda self: self.env.user,
        index=True, help='Persona responsable de mantener este manual vigente.')
    review_interval_days = fields.Integer(
        string='Revisar cada (días)', default=90,
        help='Después de este plazo el manual aparecerá como pendiente de revisión.')
    last_reviewed_at = fields.Datetime(string='Última revisión', readonly=True)
    review_due_date = fields.Date(
        string='Revisión prevista', compute='_compute_review_status', store=True)
    review_state = fields.Selection([
        ('pending', 'Pendiente de indexar'),
        ('current', 'Vigente'),
        ('due', 'Requiere revisión'),
        ('archived', 'Archivado'),
    ], string='Vigencia', compute='_compute_review_status', store=True)
    source_digest = fields.Char(string='Huella de fuente', readonly=True, copy=False)
    version = fields.Integer(string='Versión', default=1, readonly=True, copy=False)
    source_updated_at = fields.Datetime(
        string='Fuente actualizada', default=fields.Datetime.now,
        readonly=True, copy=False)
    usage_count = fields.Integer(string='Consultas', readonly=True, copy=False)
    last_used_at = fields.Datetime(string='Última consulta', readonly=True, copy=False)
    memory_map_html = fields.Html(
        string='Mapa de memoria', compute='_compute_memory_map_html',
        sanitize=False, readonly=True,
        help='Vista visual de la fuente, organización, indexación y uso de este conocimiento.')

    @api.depends(
        'name', 'source_type', 'source_text', 'pdf_filename', 'state',
        'publication_state', 'organization_state', 'organized_summary',
        'chunk_count', 'version', 'usage_count', 'last_used_at',
        'indexed_at', 'review_state',
    )
    def _compute_memory_map_html(self):
        """Render a compact, explainable map without an extra JS dependency.

        ``details`` elements provide the interaction (expand/collapse) while
        keeping the map compatible with list/form popups and mobile screens.
        The source text is escaped so the visualization never renders manual
        content as HTML.
        """
        labels = {
            'text': 'Texto interno', 'pdf': 'Documento PDF',
            'pending': 'Pendiente', 'indexed': 'Indexado', 'error': 'Error',
            'published': 'Publicado para la IA', 'draft': 'Borrador',
            'archived': 'Archivado', 'raw': 'Sin organizar',
            'organized': 'Organizado localmente',
            'not_requested': 'Sin analizar', 'processing': 'Analizando',
            'needs_review': 'Listo para revisar', 'local': 'Organizador local',
            'provider': 'Proveedor IA', 'local_fallback': 'Respaldo local',
        }
        for manual in self:
            def label(value):
                return labels.get(value, value or '—')

            source_name = manual.pdf_filename if manual.source_type == 'pdf' else 'Texto introducido en Odoo'
            source_detail = (manual.source_text or '').strip() if manual.source_type == 'text' else source_name
            source_detail = source_detail[:420] or 'Sin contenido de fuente.'
            summary = (manual.organized_summary or '').strip()[:420]
            analysis = label(getattr(manual, 'analysis_state', False))
            confidence = getattr(manual, 'analysis_confidence', 0.0) or 0.0
            nodes = [
                ('Fuente original', label(manual.source_type), source_detail),
                ('Organización', label(manual.organization_state), summary or 'Todavía no hay un resumen organizado.'),
                ('Indexación', label(manual.state), '%s fragmento(s) · versión %s' % (manual.chunk_count or 0, manual.version or 1)),
                ('Disponibilidad', label(manual.publication_state), 'Vigencia: %s · revisión: %s' % (label(manual.review_state), manual.review_due_date or 'sin fecha')),
                ('Análisis opcional', analysis, 'Confianza: %.0f%% · no cambia la fuente ni publica automáticamente.' % (confidence * 100)),
                ('Uso en conversaciones', '%s consulta(s)' % (manual.usage_count or 0), 'Última consulta: %s' % (manual.last_used_at or 'aún no consultado')),
                ('Datos vivos', 'Catálogo Odoo conectado', 'Productos, precios y disponibilidad se consultan en tiempo real cuando la pregunta coincide; no se copian al manual.'),
            ]
            cards = []
            for index, (title, status, detail) in enumerate(nodes):
                open_attr = ' open' if index in (0, 2) else ''
                cards.append(Markup(
                    '<details class="o_chatroom_memory_node"%s>'
                    '<summary><span class="o_chatroom_memory_node_icon">%s</span>'
                    '<span class="o_chatroom_memory_node_title">%s</span>'
                    '<span class="o_chatroom_memory_node_status">%s</span></summary>'
                    '<div class="o_chatroom_memory_node_detail">%s</div></details>'
                    % (open_attr, index + 1, escape(title), escape(status), escape(detail))))
            manual.memory_map_html = Markup(
                '<div class="o_chatroom_memory_map">'
                '<div class="o_chatroom_memory_header"><div>'
                '<span class="o_chatroom_memory_kicker">MEMORIA DEL AGENTE</span>'
                '<h3>%s</h3><p>Así se transforma la información antes de llegar a una respuesta.</p>'
                '</div><div class="o_chatroom_memory_core">✦<span>IA</span></div></div>'
                '<div class="o_chatroom_memory_grid">%s</div>'
                '</div>' % (escape(manual.name or 'Conocimiento'), Markup('').join(cards))
            )

    @api.depends('active', 'state', 'indexed_at', 'last_reviewed_at', 'review_interval_days')
    def _compute_review_status(self):
        today = fields.Date.context_today(self)
        for manual in self:
            if not manual.active:
                manual.review_due_date = False
                manual.review_state = 'archived'
                continue
            if manual.state != 'indexed':
                manual.review_due_date = False
                manual.review_state = 'pending'
                continue
            reviewed_at = manual.last_reviewed_at or manual.indexed_at
            due_date = fields.Date.to_date(reviewed_at) + timedelta(
                days=max(manual.review_interval_days or 90, 1)) if reviewed_at else False
            manual.review_due_date = due_date
            manual.review_state = 'due' if due_date and due_date <= today else 'current'

    @api.constrains('review_interval_days')
    def _check_review_interval(self):
        for manual in self:
            if manual.review_interval_days < 1:
                raise ValidationError(_('El intervalo de revisión debe ser de al menos 1 día.'))

    @api.constrains('source_type', 'pdf_file', 'source_text')
    def _check_knowledge_source(self):
        for manual in self:
            if manual.source_type == 'pdf' and not manual.pdf_file:
                raise ValidationError(_('Selecciona un archivo PDF para indexar este conocimiento.'))
            if manual.source_type == 'text' and not (manual.source_text or '').strip():
                raise ValidationError(_('Escribe el contenido interno antes de indexar.'))

    def write(self, vals):
        source_changed = bool({'source_type', 'source_text', 'pdf_file', 'pdf_filename'} & set(vals))
        result = super().write(vals)
        if source_changed:
            # La versión anterior no vuelve a estar disponible para la IA
            # hasta que el usuario pulse Indexar. Así nunca se mezclan datos
            # viejos y nuevos ni se hace una llamada extra al proveedor.
            for manual in self:
                super(AiKnowledgeBase, manual).write({
                    'state': 'pending', 'source_digest': False,
                    'content_text': False, 'chunk_count': 0,
                    'processing_error': False, 'indexed_at': False,
                    'last_reviewed_at': False,
                    'publication_state': 'draft', 'published_at': False,
                    'ocr_status': 'required' if manual.source_type == 'pdf' else 'not_needed',
                    'ocr_text': False,
                    'organization_state': 'raw', 'organized_summary': False,
                    'key_points': False, 'faq_entries': False,
                    'operational_rules': False, 'organized_text': False,
                    'organization_notes': False,
                    'version': (manual.version or 0) + 1,
                    'source_updated_at': fields.Datetime.now(),
                })
        return result

    def action_publish(self):
        for manual in self:
            if manual.state != 'indexed':
                raise UserError(_('Indexa el conocimiento antes de publicarlo para la IA.'))
            manual.write({'publication_state': 'published', 'published_at': fields.Datetime.now()})
        return True

    def action_unpublish(self):
        self.write({'publication_state': 'draft', 'published_at': False})
        return True

    def action_mark_reviewed(self):
        """Confirma que la fuente sigue vigente sin pagar una reindexación."""
        self.write({'last_reviewed_at': fields.Datetime.now()})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Conocimiento revisado'),
                'message': _('%s manual(es) marcado(s) como vigente(s).') % len(self),
                'type': 'success', 'sticky': False,
            },
        }

    @staticmethod
    def _extract_pdf_text(raw):
        """Extract selectable text with either supported PDF library."""
        if not raw:
            raise UserError(_('El archivo PDF está vacío.'))
        if not raw.lstrip().startswith(b'%PDF'):
            raise UserError(_('El archivo seleccionado no parece ser un PDF válido.'))
        try:
            from pypdf import PdfReader
        except ImportError:
            try:
                from PyPDF2 import PdfReader
            except ImportError:
                raise UserError(_('Para indexar PDF instala pypdf o PyPDF2 en el entorno de Odoo.'))
        try:
            reader = PdfReader(io.BytesIO(raw))
            if getattr(reader, 'is_encrypted', False):
                try:
                    if not reader.decrypt(''):
                        raise UserError(_('El PDF está protegido con contraseña y no se puede indexar.'))
                except UserError:
                    raise
                except Exception:
                    raise UserError(_('El PDF está protegido con contraseña y no se puede indexar.'))
            return '\n'.join(page.extract_text() or '' for page in reader.pages)
        except UserError:
            raise
        except Exception as error:
            _logger.warning('PDF inválido o no legible para conocimiento IA: %s', error)
            raise UserError(_('No se pudo leer el PDF. Verifica que no esté dañado y que tenga texto seleccionable.'))

    def action_index(self):
        for manual in self:
            try:
                digest = manual._get_source_digest()
                # Indexar es una operación local y no consume tokens, pero no
                # tiene sentido volver a leer un PDF o reconstruir sus
                # fragmentos si la fuente no cambió.
                if (manual.state == 'indexed' and manual.source_digest == digest
                        and manual.content_text):
                    continue
                if manual.source_type == 'text':
                    text = manual.source_text or ''
                else:
                    raw = base64.b64decode(manual.pdf_file or b'')
                    text = manual.ocr_text or self._extract_pdf_text(raw)
                if not text.strip():
                    raise UserError(_(
                        'El PDF no contiene texto seleccionable. Si es un escaneo, conviértelo con OCR o carga una versión con texto.'
                    ))
                chunks = [text[index:index + 4000] for index in range(0, len(text), 4000)]
                manual.write({
                    'content_text': '\n\n'.join(chunks), 'chunk_count': len(chunks),
                    'state': 'indexed', 'processing_error': False,
                    'indexed_at': fields.Datetime.now(),
                    'last_reviewed_at': fields.Datetime.now(),
                    'source_digest': digest,
                    'ocr_status': 'processed' if manual.ocr_text else 'not_needed',
                })
            except Exception as error:
                _logger.exception('No se pudo indexar el manual IA %s', manual.id)
                manual.write({
                    'state': 'error', 'processing_error': str(error),
                    'ocr_status': 'required' if manual.source_type == 'pdf' else manual.ocr_status,
                })
        return True

    def action_ocr(self):
        """Try optional local OCR and keep a clear fallback when unavailable."""
        for manual in self:
            if manual.source_type != 'pdf' or not manual.pdf_file:
                raise UserError(_('Selecciona un PDF antes de aplicar OCR.'))
            try:
                from pdf2image import convert_from_bytes
                import pytesseract
            except ImportError:
                manual.write({
                    'ocr_status': 'unavailable',
                    'organization_notes': _('OCR no está instalado en el entorno. Instala pdf2image, pytesseract y Tesseract para procesar PDFs escaneados.'),
                })
                continue
            try:
                raw = base64.b64decode(manual.pdf_file or b'')
                images = convert_from_bytes(raw, dpi=180, first_page=1, last_page=50)
                text = '\n\n'.join(pytesseract.image_to_string(image, lang='spa+eng') for image in images).strip()
                if not text:
                    manual.write({'ocr_status': 'required', 'organization_notes': _('OCR no encontró texto legible en el PDF.')})
                    continue
                manual.write({
                    'ocr_text': text, 'ocr_status': 'processed', 'state': 'pending',
                    'content_text': False, 'chunk_count': 0, 'source_digest': False,
                    'processing_error': False,
                })
                manual.action_index()
            except Exception as error:
                manual.write({'ocr_status': 'required', 'processing_error': str(error)})
        return True

    @staticmethod
    def _organize_natural_text(text, knowledge_format='natural'):
        """Turn everyday notes into a predictable local knowledge card.

        Organizing is deterministic and local: it is reproducible and does
        not send the company's source material to an AI provider.
        """
        clean = re.sub(r'\r\n?', '\n', text or '')
        lines = [re.sub(r'\s+', ' ', line).strip() for line in clean.split('\n')]
        lines = [line for line in lines if line]
        if not lines:
            return {'summary': '', 'points': '', 'faq': '', 'rules': '', 'structured': ''}
        paragraphs = [part.strip() for part in re.split(r'\n\s*\n+', clean) if part.strip()]
        summary = re.sub(r'\s+', ' ', paragraphs[0] if paragraphs else ' '.join(lines[:3])).strip()[:700]
        bullets, questions, rules = [], [], []
        for index, line in enumerate(lines):
            normalized = line.lstrip('-*•0123456789. ').strip()
            if len(normalized) >= 12 and (line.startswith(('-', '*', '•')) or line[:1].isdigit()):
                bullets.append(normalized[:500])
            if '?' in line or line.lower().startswith(('pregunta:', '¿')):
                answer = lines[index + 1] if index + 1 < len(lines) else ''
                questions.append('Pregunta: %s\nRespuesta: %s' % (line, answer))
            if re.search(r'\b(si|no|debe|deben|permitido|prohibido|máximo|mínimo|horario|precio|tarifa|usd)\b|\$', line, re.IGNORECASE):
                rules.append(normalized[:500])
        points = list(dict.fromkeys(bullets or lines[1:6]))[:12]
        questions = list(dict.fromkeys(questions))[:10]
        rules = list(dict.fromkeys(rules))[:12]
        label = {
            'faq': 'Preguntas frecuentes', 'policy': 'Políticas y condiciones',
            'product': 'Producto o servicio', 'playbook': 'Procedimiento comercial',
        }.get(knowledge_format, 'Conocimiento general')
        parts = [
            '[TIPO: %s]\n%s' % (label, summary),
            '[RESUMEN]\n%s' % summary,
            '[PUNTOS CLAVE]\n%s' % '\n'.join('- %s' % item for item in points),
        ]
        if questions:
            parts.append('[PREGUNTAS FRECUENTES]\n%s' % '\n\n'.join(questions))
        if rules:
            parts.append('[REGLAS OPERATIVAS]\n%s' % '\n'.join('- %s' % item for item in rules))
        parts.append('[CONTENIDO ORIGINAL]\n%s' % clean.strip())
        return {
            'summary': summary,
            'points': '\n'.join('- %s' % item for item in points),
            'faq': '\n\n'.join(questions),
            'rules': '\n'.join('- %s' % item for item in rules),
            'structured': '\n\n'.join(parts),
        }

    def action_organize(self):
        for manual in self:
            if manual.state != 'indexed' or not manual.content_text:
                manual.action_index()
            source = manual.source_text if manual.source_type == 'text' else manual.content_text
            if not (source or '').strip():
                manual.write({
                    'organization_state': 'raw',
                    'organization_notes': _('No hay contenido para organizar. Escribe texto o indexa un PDF primero.'),
                })
                continue
            organized = self._organize_natural_text(source, manual.knowledge_format)
            manual.write({
                'organization_state': 'organized',
                'organized_summary': organized['summary'],
                'key_points': organized['points'],
                'faq_entries': organized['faq'],
                'operational_rules': organized['rules'],
                'organized_text': organized['structured'],
                'content_text': organized['structured'],
                'chunk_count': max(1, (len(organized['structured']) + 3999) // 4000),
                'organization_notes': _('Organizado localmente: no consume tokens. Puedes editar el texto original y volver a organizarlo.'),
            })
        return True

    def _get_source_digest(self):
        """Huella local para evitar reprocesar una fuente sin cambios."""
        self.ensure_one()
        if self.source_type == 'pdf':
            source = base64.b64decode(self.pdf_file or b'')
        else:
            source = (self.source_text or '').encode('utf-8')
        return hashlib.sha256(
            ('%s:' % (self.source_type or 'text')).encode('utf-8') + source
        ).hexdigest()

    @api.model
    def get_sales_context(self, channel, query=''):
        return self.get_sales_context_details(channel, query=query).get('context', '')

    @api.model
    def get_sales_context_details(self, channel=False, query='', partner=False, company=False):
        """Recupera contexto y devuelve trazabilidad para revisión humana.

        La recuperación sigue siendo local por palabras clave; no llama al
        proveedor de IA. ``get_sales_context`` conserva la API anterior para
        que los demás módulos no tengan que conocer estos detalles.
        """
        icp = self.env['ir.config_parameter'].sudo()

        # El perfil activo pertenece al módulo separado de autonomía. Se
        # consulta de forma opcional para mantener compatible este motor si
        # autonomía no está instalada.
        profile = self.browse()
        profile_model = self.env['chatroom.ai.knowledge.profile'] if 'chatroom.ai.knowledge.profile' in self.env else False
        if profile_model is not False:
            try:
                profile_id = int(icp.get_param('chatroom_ai.knowledge_profile_id', 0) or 0)
            except (TypeError, ValueError):
                profile_id = 0
            if profile_id:
                profile = profile_model.sudo().browse(profile_id).exists()
                if profile and (not profile.active or profile.state != 'ready'):
                    profile = self.browse()

        include_company = profile.include_company if profile else True
        include_products = profile.include_products if profile else True
        include_stock = profile.include_stock if profile else True
        include_customer = profile.include_customer if profile else True
        include_rfm = profile.include_rfm if profile else True

        def bounded_param(key, default, minimum, maximum):
            try:
                value = int(icp.get_param(key, default))
            except (TypeError, ValueError):
                value = default
            return max(minimum, min(value, maximum))

        max_chars = profile.context_max_chars if profile else bounded_param(
            'chatroom_ai.knowledge_context_max_chars', 7000, 3000, 12000)
        max_chunks = bounded_param('chatroom_ai.knowledge_context_max_chunks', 3, 1, 5)
        company = (channel.company_id if channel else False) or company or self.env.company
        partner = (channel.partner_id if channel else False) or partner
        manuals = self.search([
            ('active', '=', True), ('state', '=', 'indexed'),
            ('publication_state', '=', 'published'),
            '|', ('company_id', '=', False), ('company_id', '=', company.id),
        ], order='priority desc, name')
        terms = set(re.findall(r'[\wáéíóúñü]{4,}', (query or '').lower()))
        stopwords = {'para', 'como', 'esta', 'este', 'cliente', 'quiero', 'necesito', 'tiene', 'desde', 'con', 'una', 'uno', 'sobre', 'debe'}
        terms -= stopwords
        ranked = []
        for manual in manuals:
            manual_terms = set(re.findall(r'[\wáéíóúñü]{3,}', (manual.keyword_tags or '').lower()))
            chunks = [chunk.strip() for chunk in (manual.content_text or '').split('\n\n') if chunk.strip()]
            for chunk in chunks:
                score = sum(1 for term in terms if term in chunk.lower())
                score += sum(2 for term in terms if term in manual_terms)
                ranked.append((score, manual.name, chunk, manual.id))
        ranked.sort(key=lambda item: item[0], reverse=True)
        # Si la pregunta contiene términos, no enviamos manuales sin ninguna
        # coincidencia. Esto evita pagar contexto irrelevante en cada turno.
        if terms:
            ranked = [item for item in ranked if item[0] > 0]
        selected = ranked[:max_chunks]
        selected_manual_ids = {item[3] for item in selected}
        selected_manuals = self.browse(selected_manual_ids)
        now = fields.Datetime.now()
        stale_usage = selected_manuals.filtered(
            lambda manual: not manual.last_used_at
            or manual.last_used_at < now - timedelta(hours=1))
        for manual in stale_usage:
            manual.sudo().write({'usage_count': manual.usage_count + 1, 'last_used_at': now})
        text = '\n\n'.join(f'[{name}]\n{chunk}' for _score, name, chunk, _manual_id in selected)
        context_parts = []
        company_data = [
            'Empresa: %s' % (company.name or ''),
            'Moneda: %s' % (company.currency_id.name or '') if company.currency_id else '',
            'Teléfono: %s' % (company.phone or ''),
            'Correo: %s' % (company.email or ''),
            'Dirección: %s' % ', '.join(filter(None, [company.street, company.city, company.country_id.name])),
        ]
        if include_company:
            context_parts.append('Datos actuales de la empresa en Odoo:\n%s' % '\n'.join(
                item for item in company_data if item.split(': ', 1)[-1]))

        product_context = self._get_product_context(
            company, query, include_stock=include_stock, partner=partner
        ) if include_products else ''
        if product_context:
            context_parts.append(product_context)
        if partner and include_customer:
            rfm_text = getattr(partner, 'rfm_category', '') if include_rfm else ''
            context_parts.append(
                'Ficha comercial actual del cliente:\n' +
                f'Cliente: {partner.name}; categoría RFM: {rfm_text}; '
                f'productos comprados: {getattr(partner, "commercial_top_product_summary", "")}.'
            )
        if text:
            context_parts.append('Manuales y políticas internas relevantes:\n%s' % text)
        context = '\n\n'.join(context_parts)[:max_chars]
        sources = []
        for manual_id in selected_manual_ids:
            manual = self.browse(manual_id)
            rows = [item for item in selected if item[3] == manual_id]
            sources.append({
                'id': manual.id, 'name': manual.name, 'category': manual.category,
                'score': max((item[0] for item in rows), default=0),
                'chunks': len(rows),
                'version': manual.version,
                'review_state': manual.review_state,
            })
        sources.sort(key=lambda item: (-item['score'], item['name']))
        live_sources = [
            'Empresa y moneda' if include_company else '',
            'Productos coincidentes de Odoo' if product_context else '',
            'Ficha del cliente' if partner and include_customer else '',
            'RFM del cliente' if partner and include_customer and include_rfm else '',
        ]
        return {
            'context': context,
            'sources': sources,
            'live_sources': [source for source in live_sources if source],
            'estimated_input_tokens': max(1, (len(context) + 3) // 4) if context else 0,
            'context_chars': len(context),
        }

    def _get_product_context(self, company, query, include_stock=True, partner=False):
        """Consulta productos vivos de Odoo; nunca copia un catálogo completo."""
        if 'product.product' not in self.env or not query:
            return ''
        stopwords = {
            'para', 'como', 'esta', 'este', 'cliente', 'quiero', 'necesito',
            'tiene', 'desde', 'con', 'una', 'uno', 'sobre', 'debe', 'precio',
            'cuanto', 'cuánto', 'disponible', 'stock', 'producto',
        }
        terms = [term for term in re.findall(r'[\wáéíóúñü]{3,}', query.lower())
                 if term not in stopwords][:6]
        if not terms:
            return ''
        product_domain = []
        for term in terms:
            term_domain = [
                '|', '|',
                ('name', 'ilike', term),
                ('default_code', 'ilike', term),
                ('description_sale', 'ilike', term),
            ]
            product_domain = term_domain if not product_domain else ['|'] + product_domain + term_domain
        icp = self.env['ir.config_parameter'].sudo()
        try:
            product_limit = int(icp.get_param('chatroom_ai.knowledge_product_limit', 5))
        except (TypeError, ValueError):
            product_limit = 5
        product_limit = max(1, min(product_limit, 8))
        products = self.env['product.product'].search(
            product_domain, order='name asc', limit=product_limit)
        if not products:
            return ''
        pricelist = False
        if partner and 'property_product_pricelist' in partner._fields:
            pricelist = partner.with_company(company).property_product_pricelist
        currency = pricelist.currency_id if pricelist else company.currency_id
        rows = []
        for product in products:
            product_company = product.with_company(company)
            try:
                price = pricelist._get_product_price(product_company, 1.0) if pricelist else product_company.lst_price
            except (AttributeError, TypeError, ValueError):
                price = product_company.lst_price
            row = '- %s | código: %s | precio de venta: %.2f %s' % (
                product.display_name,
                product.default_code or 'sin código',
                price,
                (currency.symbol or currency.name) if currency else '',
            )
            if include_stock:
                available = (
                    product_company.free_qty if 'free_qty' in product_company._fields
                    else product_company.qty_available
                ) if product_company.type != 'service' else False
                row += ' | disponible: %s' % (
                    'servicio' if product_company.type == 'service' else f'{available:g}'
                )
            rows.append(row)
        return 'Datos vivos de productos en Odoo (consultados ahora):\n%s' % '\n'.join(rows)

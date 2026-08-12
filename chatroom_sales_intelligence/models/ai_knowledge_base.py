# -*- coding: utf-8 -*-
import base64
import io
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AiKnowledgeBase(models.Model):
    _name = 'ai.knowledge.base'
    _description = 'Manual interno para asistencia IA'
    _order = 'name'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    pdf_file = fields.Binary(string='Manual PDF', attachment=True, required=True)
    pdf_filename = fields.Char(string='Nombre del archivo')
    content_text = fields.Text(string='Texto indexado', readonly=True)
    chunk_count = fields.Integer(readonly=True)
    state = fields.Selection([
        ('pending', 'Pendiente'), ('indexed', 'Indexado'), ('error', 'Error'),
    ], default='pending', readonly=True)
    processing_error = fields.Text(readonly=True)

    def action_index(self):
        for manual in self:
            try:
                raw = base64.b64decode(manual.pdf_file or b'')
                try:
                    from pypdf import PdfReader
                    reader = PdfReader(io.BytesIO(raw))
                    text = '\n'.join(page.extract_text() or '' for page in reader.pages)
                except ImportError:
                    text = raw.decode('utf-8', errors='ignore')
                if not text.strip():
                    raise UserError(_('No se pudo extraer texto del PDF.'))
                chunks = [text[index:index + 4000] for index in range(0, len(text), 4000)]
                manual.write({
                    'content_text': '\n\n'.join(chunks), 'chunk_count': len(chunks),
                    'state': 'indexed', 'processing_error': False,
                })
            except Exception as error:
                _logger.exception('No se pudo indexar el manual IA %s', manual.id)
                manual.write({'state': 'error', 'processing_error': str(error)})
        return True

    @api.model
    def get_sales_context(self, channel):
        manuals = self.search([('active', '=', True), ('state', '=', 'indexed')])
        if not manuals:
            return ''
        text = '\n\n'.join(
            f'[{manual.name}]\n{manual.content_text or ""}' for manual in manuals)
        partner = channel.partner_id
        customer_context = ''
        if partner:
            customer_context = (
                f'Cliente: {partner.name}; categoría RFM: {getattr(partner, "rfm_category", "")}; '
                f'productos comprados: {getattr(partner, "commercial_top_product_summary", "")}'
            )
        return f'{customer_context}\n\nManuales internos:\n{text}'[:12000]

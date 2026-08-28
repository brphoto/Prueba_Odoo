# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ChatroomAiKnowledgeComposer(models.TransientModel):
    """Simple, non-technical entry point for internal AI knowledge."""

    _name = 'chatroom.ai.knowledge.composer'
    _description = 'Crear conocimiento IA desde lenguaje natural'

    name = fields.Char(string='Nombre del conocimiento', required=True)
    company_id = fields.Many2one(
        'res.company', string='Empresa', default=lambda self: self.env.company)
    category = fields.Selection([
        ('general', 'General'), ('products', 'Productos y servicios'),
        ('sales', 'Ventas'), ('support', 'Soporte'),
        ('payments', 'Pagos y facturación'),
        ('policies', 'Políticas y condiciones'),
    ], string='Categoría', default='general', required=True)
    knowledge_format = fields.Selection([
        ('natural', 'Texto natural'), ('faq', 'Preguntas frecuentes'),
        ('policy', 'Política o regla'), ('product', 'Producto o servicio'),
        ('playbook', 'Procedimiento comercial'),
    ], string='Tipo de contenido', default='natural', required=True)
    source_type = fields.Selection([
        ('text', 'Texto natural'),
        ('pdf', 'Documento PDF'),
    ], string='Fuente', default='text', required=True,
        help='Usa texto para notas y políticas, o PDF para manuales y documentos.')
    pdf_file = fields.Binary(string='Archivo PDF', attachment=True)
    pdf_filename = fields.Char(string='Nombre del archivo')
    keyword_tags = fields.Char(
        string='Palabras clave',
        help='Opcional. Separa términos por coma para ayudar a encontrar esta información.')
    source_text = fields.Text(
        string='Información para la IA',
        help='Escribe la información como la explicarías a un compañero. No necesitas usar un formato técnico.')

    @api.onchange('knowledge_format')
    def _onchange_knowledge_format(self):
        if self.source_text:
            return
        templates = {
            'faq': _('Pregunta: ¿Qué ofrecemos?\nRespuesta: Escribe aquí la respuesta aprobada.'),
            'policy': _('Regla: Para cotizar necesitamos conocer el alcance, usuarios y fecha objetivo.\nExcepción: Escalar a un responsable cuando el caso no esté definido.'),
            'product': _('Producto o servicio: Nombre\nDescripción: Qué resuelve y para quién.\nPrecio o referencia: Completar si aplica.\nCondiciones: Garantía, tiempos y restricciones.'),
            'playbook': _('Paso 1: Identificar la necesidad.\nPaso 2: Consultar productos y condiciones.\nPaso 3: Preparar una propuesta.\nEscalar cuando: falten datos o se requiera una aprobación.'),
        }
        self.source_text = templates.get(self.knowledge_format, '')

    def action_load_template(self):
        self._onchange_knowledge_format()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Crear conocimiento IA'),
            'res_model': self._name,
            'view_mode': 'form', 'res_id': self.id, 'target': 'new',
        }

    def action_create(self):
        self.ensure_one()
        if self.source_type == 'pdf' and not self.pdf_file:
            raise UserError(_('Selecciona un archivo PDF antes de continuar.'))
        if self.source_type == 'text' and not (self.source_text or '').strip():
            raise UserError(_('Escribe la información antes de guardarla.'))
        values = {
            'name': self.name,
            'company_id': self.company_id.id,
            'category': self.category,
            'knowledge_format': self.knowledge_format,
            'source_type': self.source_type,
            'keyword_tags': self.keyword_tags,
            'source_text': self.source_text,
            'pdf_file': self.pdf_file,
            'pdf_filename': self.pdf_filename,
        }
        manual = self.env['ai.knowledge.base'].create(values)
        manual.action_organize()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Conocimiento creado'),
            'res_model': 'ai.knowledge.base',
            'view_mode': 'form', 'res_id': manual.id, 'target': 'current',
        }

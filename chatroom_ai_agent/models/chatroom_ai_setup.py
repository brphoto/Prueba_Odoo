# -*- coding: utf-8 -*-
import importlib.util
import shutil

from odoo import _, api, fields, models


class ChatroomAiSetup(models.TransientModel):
    _name = 'chatroom.ai.setup'
    _description = 'Checklist de preparación del Agente IA'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(default='Preparación del sistema comercial', readonly=True)
    refreshed_at = fields.Datetime(string='Última revisión', readonly=True)
    whatsapp_ready = fields.Boolean(string='WhatsApp conectado', readonly=True)
    whatsapp_detail = fields.Char(readonly=True)
    provider_ready = fields.Boolean(string='Proveedor IA configurado', readonly=True)
    provider_detail = fields.Char(readonly=True)
    knowledge_ready = fields.Boolean(string='Conocimiento disponible', readonly=True)
    knowledge_detail = fields.Char(readonly=True)
    sales_ready = fields.Boolean(string='Ventas autónomas disponibles', readonly=True)
    sales_detail = fields.Char(readonly=True)
    payment_ready = fields.Boolean(string='Pagos disponibles', readonly=True)
    payment_detail = fields.Char(readonly=True)
    security_ready = fields.Boolean(string='Seguridad configurada', readonly=True)
    security_detail = fields.Char(readonly=True)
    python_dependencies_ready = fields.Boolean(string='Dependencias Python', readonly=True)
    python_dependencies_detail = fields.Char(string='Detalle de dependencias', readonly=True)
    ocr_ready = fields.Boolean(string='OCR para PDF escaneado', readonly=True)
    ocr_detail = fields.Char(string='Detalle de OCR', readonly=True)
    ready_count = fields.Integer(string='Comprobaciones correctas', readonly=True)
    total_checks = fields.Integer(string='Comprobaciones totales', default=8, readonly=True)
    readiness_percent = fields.Float(string='Preparación (%)', readonly=True)
    overall_state = fields.Selection([
        ('ready', 'Listo para operar'),
        ('attention', 'Requiere configuración'),
    ], string='Estado general', readonly=True)

    @api.model
    def action_open(self):
        record = self.create({})
        record._refresh()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Preparación del sistema'),
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': record.id,
            'target': 'current',
        }

    def _refresh(self):
        self.ensure_one()
        icp = self.env['ir.config_parameter'].sudo()
        whatsapp = bool(
            icp.get_param('chatroom_whatsapp.access_token') and
            icp.get_param('chatroom_whatsapp.phone_number_id'))
        if 'chatroom.whatsapp.number' in self.env:
            whatsapp = whatsapp or bool(self.env['chatroom.whatsapp.number'].sudo().search_count([
                ('active', '=', True), ('phone_number_id', '!=', False),
            ]))
        provider = bool(
            icp.get_param('chatroom_whatsapp.ai_provider_url') and
            icp.get_param('chatroom_whatsapp.ai_api_key'))
        if 'chatroom.ai.provider.model' in self.env:
            provider = provider or bool(self.env['chatroom.ai.provider.model'].sudo().search_count([
                ('active', '=', True),
            ]))
        knowledge = False
        knowledge_count = 0
        if 'ai.knowledge.base' in self.env:
            knowledge_count = self.env['ai.knowledge.base'].sudo().search_count([
                ('active', '=', True), ('state', '=', 'indexed'),
            ])
            knowledge = bool(knowledge_count)
        sales = 'sale.order' in self.env
        payment = 'chatroom.payment.link' in self.env
        require_approval = icp.get_param('chatroom_ai_agent.require_approval', 'True') == 'True'
        safety_profile = icp.get_param('chatroom_ai_agent.safety_profile', 'supervised')
        security = require_approval or safety_profile == 'supervised'

        required_python = ('requests', 'pypdf')
        missing_python = [name for name in required_python
                          if importlib.util.find_spec(name) is None]
        python_ready = not missing_python
        ocr_python = all(importlib.util.find_spec(name) is not None
                          for name in ('pdf2image', 'pytesseract'))
        tesseract_ready = bool(shutil.which('tesseract'))
        poppler_ready = bool(shutil.which('pdftoppm'))
        ocr_ready = ocr_python and tesseract_ready and poppler_ready

        values = {
            'refreshed_at': fields.Datetime.now(),
            'whatsapp_ready': whatsapp,
            'whatsapp_detail': _('Configurado') if whatsapp else _('Falta el token y el Phone Number ID.'),
            'provider_ready': provider,
            'provider_detail': _('Modelo listo para usar') if provider else _('Configura un proveedor o modelo IA.'),
            'knowledge_ready': knowledge,
            'knowledge_detail': _('%s manual(es) indexado(s)') % knowledge_count if knowledge else _('Indexa al menos un manual activo.'),
            'sales_ready': sales,
            'sales_detail': _('Módulo de ventas disponible') if sales else _('Instala Ventas para activar este flujo.'),
            'payment_ready': payment,
            'payment_detail': _('Conector de links disponible') if payment else _('Instala el módulo de links de pago.'),
            'security_ready': security,
            'security_detail': _('Aprobación humana protegida') if security else _('Activa la aprobación humana.'),
            'python_dependencies_ready': python_ready,
            'python_dependencies_detail': _('requests y pypdf disponibles') if python_ready else _('Faltan: %s') % ', '.join(missing_python),
            'ocr_ready': ocr_ready,
            'ocr_detail': _('OCR Python, Tesseract y Poppler disponibles') if ocr_ready else _(
                'OCR Python: %s · Tesseract: %s · Poppler: %s') % (
                    _('listo') if ocr_python else _('falta'),
                    _('listo') if tesseract_ready else _('falta'),
                    _('listo') if poppler_ready else _('falta')),
        }
        checks = (
            'whatsapp_ready', 'provider_ready', 'knowledge_ready',
            'sales_ready', 'payment_ready', 'security_ready',
            'python_dependencies_ready', 'ocr_ready')
        ready_count = sum(bool(values[field]) for field in checks)
        values.update({
            'ready_count': ready_count,
            # El widget percentage de Odoo recibe un valor entre 0 y 1.
            # Guardar 87.5 aquí producía 8750% en pantalla.
            'readiness_percent': ready_count / 8.0,
            'overall_state': 'ready' if ready_count == 8 else 'attention',
        })
        self.write(values)
        return self

    def action_refresh(self):
        self._refresh()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Checklist actualizado'),
                'message': _('%s de %s comprobaciones listas.') % (self.ready_count, self.total_checks),
                'type': 'success' if self.overall_state == 'ready' else 'warning',
                'sticky': False,
            },
        }

# -*- coding: utf-8 -*-
"""Comprobaciones locales de preparación operativa de Chatroom."""

import importlib.util

from odoo import _, api, fields, models


class ChatroomOperationsCheck(models.Model):
    _name = 'chatroom.operations.check'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Comprobación de preparación de Chatroom'
    _order = 'sequence, category, id'

    name = fields.Char(string='Comprobación', required=True, tracking=True)
    code = fields.Char(string='Código', required=True, index=True, copy=False)
    sequence = fields.Integer(default=10, index=True)
    category = fields.Selection([
        ('connection', 'Conexiones'),
        ('knowledge', 'Conocimiento'),
        ('commercial', 'Operación comercial'),
        ('security', 'Seguridad'),
        ('platform', 'Plataforma'),
    ], string='Área', required=True, default='platform', index=True)
    company_id = fields.Many2one(
        'res.company', string='Empresa', required=True, index=True,
        default=lambda self: self.env.company)
    required = fields.Boolean(
        string='Bloqueante', default=False, tracking=True,
        help='Debe estar correcto para considerar lista la operación.')
    state = fields.Selection([
        ('ok', 'Correcto'), ('warning', 'Requiere configuración'),
        ('error', 'Error'), ('not_installed', 'Módulo opcional no instalado'),
    ], string='Estado', required=True, default='warning', tracking=True, index=True)
    detail = fields.Text(string='Detalle', readonly=True)
    recommendation = fields.Text(string='Qué hacer', readonly=True)
    checked_at = fields.Datetime(string='Última comprobación', readonly=True)
    active = fields.Boolean(default=True)

    _code_company_unique = models.Constraint(
        'unique(code, company_id)',
        'El código de la comprobación debe ser único por empresa.',
    )

    @api.model
    def _has_model(self, model_name):
        return model_name in self.env

    @api.model
    def _param_enabled(self, key, default=False):
        raw = self.env['ir.config_parameter'].sudo().get_param(key)
        if raw in (False, None, ''):
            return default
        return str(raw).strip().lower() in ('1', 'true', 'yes', 'on')

    @api.model
    def _definitions(self):
        return [
            {'code': 'whatsapp_connection', 'name': _('WhatsApp conectado'), 'category': 'connection', 'sequence': 10, 'required': True},
            {'code': 'ai_provider', 'name': _('Proveedor IA configurado'), 'category': 'connection', 'sequence': 20, 'required': False},
            {'code': 'knowledge_indexed', 'name': _('Conocimiento indexado'), 'category': 'knowledge', 'sequence': 30, 'required': False},
            {'code': 'odoo_catalog', 'name': _('Catálogo de Odoo disponible'), 'category': 'commercial', 'sequence': 40, 'required': False},
            {'code': 'native_sales', 'name': _('Ventas nativas disponibles'), 'category': 'commercial', 'sequence': 50, 'required': False},
            {'code': 'native_calendar', 'name': _('Calendario nativo disponible'), 'category': 'commercial', 'sequence': 60, 'required': False},
            {'code': 'payment_connector', 'name': _('Conector de pagos disponible'), 'category': 'commercial', 'sequence': 70, 'required': False},
            {'code': 'human_approval', 'name': _('Aprobación humana protegida'), 'category': 'security', 'sequence': 80, 'required': True},
            {'code': 'python_dependencies', 'name': _('Dependencias Python básicas'), 'category': 'platform', 'sequence': 90, 'required': True},
            {'code': 'cost_tracking', 'name': _('Medición de consumo IA'), 'category': 'platform', 'sequence': 100, 'required': False},
            {'code': 'automation_history', 'name': _('Historial de automatizaciones'), 'category': 'platform', 'sequence': 110, 'required': False},
            {'code': 'native_chatter', 'name': _('Chatter nativo disponible'), 'category': 'platform', 'sequence': 120, 'required': True},
        ]

    @api.model
    def _evaluate(self, code):
        icp = self.env['ir.config_parameter'].sudo()
        if code == 'whatsapp_connection':
            if not self._has_model('chatroom.whatsapp.number'):
                return 'not_installed', _('El conector de WhatsApp no está instalado.'), _('Instala chatroom_whatsapp solo si la empresa necesita ese canal.')
            lines = self.env['chatroom.whatsapp.number'].sudo().search([('active', '=', True)])
            token = icp.get_param('chatroom_whatsapp.access_token')
            ready = any(line.phone_number_id and (line.access_token or token) for line in lines)
            return ('ok', _('Hay una línea activa con identificador y credencial.'), _('Puedes probar el webhook o generar una conversación DEMO QA.')) if ready else ('warning', _('Hay líneas activas, pero falta completar sus credenciales.'), _('Configura Phone Number ID y Token en Ajustes > Chatroom WhatsApp.'))
        if code == 'ai_provider':
            ready = bool(icp.get_param('chatroom_whatsapp.ai_provider_url') and icp.get_param('chatroom_whatsapp.ai_api_key'))
            if not ready and self._has_model('chatroom.ai.provider.model'):
                ready = bool(self.env['chatroom.ai.provider.model'].sudo().search_count([('active', '=', True)]))
            return ('ok', _('El proveedor y al menos un modelo están disponibles.'), _('Puedes ejecutar una prueba controlada desde Laboratorio IA.')) if ready else ('warning', _('No hay endpoint y modelo IA completos para producción.'), _('Configura endpoint, API Key y sincroniza los modelos.'))
        if code == 'knowledge_indexed':
            if not self._has_model('ai.knowledge.base'):
                return 'not_installed', _('El módulo de conocimiento no está instalado.'), _('Instálalo solo cuando la empresa necesite respuestas basadas en documentos o políticas.')
            count = self.env['ai.knowledge.base'].sudo().search_count([('active', '=', True), ('state', '=', 'indexed')])
            return ('ok', _('%s fuente(s) activa(s) están indexadas.') % count, _('Revisa fuentes y confianza antes de activar respuestas autónomas.')) if count else ('warning', _('No hay fuentes activas indexadas.'), _('Crea conocimiento con texto natural, catálogo Odoo o PDF con texto seleccionable.'))
        if code == 'odoo_catalog':
            if not self._has_model('product.product'):
                return 'not_installed', _('El catálogo de productos no está instalado.'), _('Instala Ventas o Inventario si se desea consultar productos y stock.')
            count = self.env['product.product'].sudo().search_count([('active', '=', True), ('sale_ok', '=', True)])
            return ('ok', _('%s producto(s) vendible(s) están disponibles para consulta.') % count, _('La IA consultará precio y disponibilidad en Odoo al responder.')) if count else ('warning', _('No hay productos vendibles activos.'), _('Activa al menos un producto vendible o configura el servicio de cotización.'))
        if code == 'native_sales':
            ready = self._has_model('sale.order') and self._has_model('sale.order.line')
            return ('ok', _('El flujo usa sale.order y sale.order.line nativos.'), _('Las cotizaciones y reportes deben generarse desde Ventas.')) if ready else ('not_installed', _('Ventas no está instalado.'), _('Instala Ventas para crear cotizaciones nativas desde conversaciones.'))
        if code == 'native_calendar':
            ready = self._has_model('calendar.event')
            return ('ok', _('Calendario nativo está disponible para crear reuniones.'), _('Las reuniones pueden usar videollamada, asistentes y recordatorios nativos.')) if ready else ('not_installed', _('Calendario no está instalado.'), _('Instala Calendario si se desea agendar desde WhatsApp.'))
        if code == 'payment_connector':
            ready = self._has_model('chatroom.payment.link')
            return ('ok', _('El modelo modular de links de pago está disponible.'), _('El proveedor concreto se selecciona por configuración.')) if ready else ('not_installed', _('No hay módulo de links de pago instalado.'), _('Instala solo el conector de pagos que la empresa vaya a utilizar.'))
        if code == 'human_approval':
            ready = self._param_enabled('chatroom_ai_agent.require_approval', True) or icp.get_param('chatroom_ai_agent.safety_profile', 'supervised') == 'supervised'
            return ('ok', _('Las acciones sensibles mantienen aprobación humana.'), _('Es el modo recomendado para cotizaciones, pedidos, pagos y mensajes.')) if ready else ('error', _('La aprobación humana está desactivada.'), _('Actívala antes de permitir autonomía comercial.'))
        if code == 'python_dependencies':
            missing = [item for item in ('requests', 'pypdf') if importlib.util.find_spec(item) is None]
            return ('ok', _('requests y pypdf están disponibles.'), _('La indexación de PDFs con texto está preparada.')) if not missing else ('error', _('Faltan: %s.') % ', '.join(missing), _('Instala las dependencias indicadas en requirements.txt.'))
        if code == 'cost_tracking':
            ready = self._has_model('chatroom.ai.usage.event') and self._has_model('chatroom.ai.usage.snapshot')
            return ('ok' if ready else 'not_installed', _('Se registra consumo local; el costo oficial requiere Admin API Key.') if ready else _('No hay modelos de medición instalados.'), _('Configura Admin API Key solo para consultar uso y costos oficiales.') if ready else _('Instala chatroom_ai_usage para medir tokens y costos.'))
        if code == 'automation_history':
            ready = self._has_model('chatroom.ai.automation') and self._has_model('chatroom.ai.automation.run')
            return ('ok' if ready else 'not_installed', _('Las automatizaciones conservan ejecuciones, tareas e incidencias.') if ready else _('No hay historial de automatizaciones instalado.'), _('Usa Ejecutar ahora y revisa la ejecución antes de activar el cron.') if ready else _('Instala el módulo Agente IA.'))
        if code == 'native_chatter':
            ready = self._has_model('mail.message') and self._has_model('mail.activity')
            return ('ok', _('El correo interno, chatter y actividades nativos están disponibles.'), _('Los documentos comerciales se mantienen en modelos nativos de Odoo.')) if ready else ('error', _('Faltan modelos base de correo interno.'), _('Verifica la instalación del módulo mail.'))
        return 'warning', _('Comprobación no definida.'), _('Revisa la configuración de esta edición.')

    @api.model
    def action_run_all(self):
        now = fields.Datetime.now()
        result = self.browse()
        for definition in self._definitions():
            record = self.sudo().search([('code', '=', definition['code']), ('company_id', '=', self.env.company.id)], limit=1)
            if not record:
                record = self.sudo().create(dict(definition, company_id=self.env.company.id))
            state, detail, recommendation = self._evaluate(definition['code'])
            record.write({'state': state, 'detail': detail, 'recommendation': recommendation, 'checked_at': now})
            result |= record
        return result

    def action_check(self):
        self.ensure_one()
        state, detail, recommendation = self._evaluate(self.code)
        self.write({'state': state, 'detail': detail, 'recommendation': recommendation, 'checked_at': fields.Datetime.now()})
        return True

    def action_run_all_ui(self):
        self.action_run_all()
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {'title': _('Comprobaciones actualizadas'), 'message': _('Se actualizaron las comprobaciones locales. No se enviaron mensajes ni se consumieron tokens.'), 'type': 'success', 'sticky': False}}

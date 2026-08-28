# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ChatroomAiSetupWizard(models.TransientModel):
    """Guided, optional first-run setup for the AI and knowledge modules.

    The wizard only calls the provider's models endpoint. It never creates a
    completion, so configuring the integration and indexing uploaded PDFs do
    not spend tokens.
    """

    _name = 'chatroom.ai.setup.wizard'
    _description = 'Asistente inicial de IA y conocimiento'

    provider_url = fields.Char(
        string='Endpoint de IA', default='https://api.openai.com/v1', required=True,
        help='Para OpenAI usa https://api.openai.com/v1. No pegues /chat/completions.')
    api_key = fields.Char(
        string='API Key para respuestas', password=True,
        help='Se guarda como parámetro protegido de Odoo. Nunca se muestra en resultados.')
    admin_api_key = fields.Char(
        string='Admin API Key para costos', password=True,
        help='Opcional. Se usa solo para consultar uso y costos oficiales de la organización.')
    enable_ai = fields.Boolean(
        string='Activar IA para Chatroom', default=True,
        help='Activa la integración después de validar la configuración.')
    selected_model_id = fields.Many2one(
        'chatroom.ai.provider.model', string='Modelo principal',
        domain=[('active', '=', True), ('supports_chat', '=', True)],
        help='Elige un modelo sincronizado; no necesitas escribir el identificador.')
    fallback_model_id = fields.Many2one(
        'chatroom.ai.provider.model', string='Modelo de respaldo',
        domain=[('active', '=', True), ('supports_chat', '=', True)])
    attachment_ids = fields.Many2many(
        'ir.attachment', string='Documentos PDF',
        help='Puedes cargar varios PDFs. Se indexan localmente y no se envían al proveedor.')
    create_company_knowledge = fields.Boolean(
        string='Crear guía inicial de la empresa', default=True,
        help='Crea una guía editable con la información comercial básica de la empresa.')
    company_knowledge_text = fields.Text(
        string='Información inicial de la empresa',
        default=lambda self: _(
            'Somos una empresa implementadora de Odoo. Ofrecemos análisis de procesos, '
            'configuración, migración de datos, capacitación y desarrollo personalizado. '
            'La tarifa referencial debe confirmarse antes de cotizar.'),
        help='Esta guía se organiza localmente para que puedas revisarla antes de publicarla.')
    initial_funding = fields.Float(
        string='Recarga inicial registrada (USD)', digits=(16, 6), default=0.0,
        help='Opcional: registra una recarga ya realizada para comparar costo oficial y saldo de control.')
    result_message = fields.Text(string='Resultado', readonly=True)

    @api.constrains('initial_funding')
    def _check_initial_funding(self):
        for wizard in self:
            if wizard.initial_funding < 0:
                raise ValidationError(_('La recarga inicial no puede ser negativa.'))

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        icp = self.env['ir.config_parameter'].sudo()
        configured_url = (icp.get_param('chatroom_whatsapp.ai_provider_url') or '').strip()
        if configured_url:
            values['provider_url'] = configured_url.removesuffix('/chat/completions').rstrip('/')
        # Do not put existing secrets back into the form, even as a password.
        models_model = self.env['chatroom.ai.provider.model']
        current = models_model.search([
            ('active', '=', True), ('supports_chat', '=', True),
        ], order='recommended desc, name', limit=1)
        if current:
            values['selected_model_id'] = current.id
        return values

    def _save_configuration(self):
        self.ensure_one()
        endpoint = (self.provider_url or '').strip().rstrip('/')
        if endpoint.endswith('/chat/completions'):
            endpoint = endpoint[:-len('/chat/completions')].rstrip('/')
        if not endpoint.startswith(('http://', 'https://')):
            raise UserError(_('El endpoint debe comenzar por http:// o https://.'))
        icp = self.env['ir.config_parameter'].sudo()
        api_key = (self.api_key or '').strip() or (icp.get_param('chatroom_whatsapp.ai_api_key') or '').strip()
        if not api_key:
            raise UserError(_('Escribe la API Key para poder probar y configurar la IA.'))
        icp.set_param('chatroom_whatsapp.ai_provider_url', endpoint)
        icp.set_param('chatroom_whatsapp.ai_api_key', api_key)
        if self.admin_api_key and self.admin_api_key.strip():
            icp.set_param('chatroom_whatsapp.ai_admin_api_key', self.admin_api_key.strip())
        icp.set_param('chatroom_whatsapp.ai_enabled', 'True' if self.enable_ai else 'False')
        if self.selected_model_id:
            icp.set_param('chatroom_whatsapp.ai_model_id', str(self.selected_model_id.id))
            icp.set_param('chatroom_whatsapp.ai_model_reply_id', str(self.selected_model_id.id))
            icp.set_param('chatroom_whatsapp.ai_model_summary_id', str(self.selected_model_id.id))
            icp.set_param('chatroom_whatsapp.ai_model_classification_id', str(self.selected_model_id.id))
            icp.set_param('chatroom_whatsapp.ai_model_next_action_id', str(self.selected_model_id.id))
            icp.set_param('chatroom_whatsapp.ai_model_agent_id', str(self.selected_model_id.id))
        if self.fallback_model_id:
            icp.set_param('chatroom_whatsapp.ai_fallback_model_id', str(self.fallback_model_id.id))
        return endpoint, api_key

    def action_sync_models(self):
        self.ensure_one()
        self._save_configuration()
        try:
            self.env['chatroom.ai.provider.model'].action_sync_from_provider()
        except UserError as error:
            self.result_message = _('Configuración guardada, pero no se pudieron sincronizar modelos: %s') % error
            return self._reload_action()
        if not self.selected_model_id:
            self.selected_model_id = self.env['chatroom.ai.provider.model'].search([
                ('active', '=', True), ('supports_chat', '=', True),
            ], order='recommended desc, name', limit=1)
            if self.selected_model_id:
                # The model may have been discovered during this same action;
                # persist it before finishing so the first real request uses it.
                self._save_configuration()
        self.result_message = _(
            'Modelos actualizados. Selecciona el modelo principal y pulsa «Finalizar».'
        )
        return self._reload_action()

    def action_test_official_costs(self):
        """Validate the administrative connection without generating AI tokens."""
        self.ensure_one()
        self._save_configuration()
        return self.env['chatroom.ai.usage.snapshot'].action_test_platform_connection()

    def _reload_action(self):
        return {
            'type': 'ir.actions.act_window', 'name': _('Asistente inicial de IA'),
            'res_model': self._name, 'view_mode': 'form', 'res_id': self.id,
            'target': 'new',
        }

    def _create_knowledge(self):
        knowledge_model = self.env['ai.knowledge.base'] if 'ai.knowledge.base' in self.env else False
        if not knowledge_model:
            return 0
        created = 0
        if self.create_company_knowledge and (self.company_knowledge_text or '').strip():
            manual = knowledge_model.create({
                'name': _('Guía inicial de la empresa'),
                'company_id': self.env.company.id,
                'category': 'general', 'knowledge_format': 'natural',
                'source_type': 'text', 'source_text': self.company_knowledge_text,
                'publication_state': 'draft',
            })
            manual.action_organize()
            created += 1
        for attachment in self.attachment_ids:
            filename = attachment.name or 'documento.pdf'
            if not filename.lower().endswith('.pdf') and attachment.mimetype != 'application/pdf':
                continue
            data = attachment.datas
            if not data:
                continue
            manual = knowledge_model.create({
                'name': filename.rsplit('.', 1)[0],
                'company_id': self.env.company.id,
                'category': 'general', 'knowledge_format': 'natural',
                'source_type': 'pdf', 'pdf_file': data, 'pdf_filename': filename,
                'publication_state': 'draft',
            })
            manual.action_index()
            created += 1
        return created

    def action_finish(self):
        self.ensure_one()
        self._save_configuration()
        if not self.selected_model_id:
            self.selected_model_id = self.env['chatroom.ai.provider.model'].search([
                ('active', '=', True), ('supports_chat', '=', True),
            ], order='recommended desc, name', limit=1)
            if self.selected_model_id:
                # Persist the model discovered during this same finish action.
                self._save_configuration()
        if not self.selected_model_id:
            try:
                self.env['chatroom.ai.provider.model'].action_sync_from_provider()
            except UserError as error:
                raise UserError(_(
                    'No hay un modelo seleccionado. Pulsa «Guardar y sincronizar modelos» '
                    'o revisa la conexión: %s') % error) from error
            self.selected_model_id = self.env['chatroom.ai.provider.model'].search([
                ('active', '=', True), ('supports_chat', '=', True),
            ], order='recommended desc, name', limit=1)
        if not self.selected_model_id:
            raise UserError(_('Sincroniza modelos y selecciona un modelo principal antes de finalizar.'))
        if self.initial_funding > 0 and 'chatroom.ai.funding' in self.env:
            self.env['chatroom.ai.funding'].create({
                'name': _('Recarga inicial registrada desde el asistente'),
                'movement_type': 'credit', 'amount': self.initial_funding,
                'currency': 'usd', 'reference': _('Asistente inicial de IA'),
            })
        try:
            created = self._create_knowledge()
        except Exception as error:  # noqa: BLE001 - se informa en el asistente
            raise UserError(_('La configuración se guardó, pero no se pudo cargar el conocimiento: %s') % error) from error
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'title': _('IA configurada'),
                'message': _('Configuración guardada. %s conocimiento(s) quedaron indexados como borrador para revisión.') % created,
                'type': 'success', 'sticky': False,
            },
        }

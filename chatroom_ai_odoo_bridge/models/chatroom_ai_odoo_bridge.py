# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ChatroomAiOdooBridge(models.Model):
    _name = 'chatroom.ai.odoo.bridge'
    _description = 'Puente entre Chatroom y la IA nativa de Odoo'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'company_id, name'

    name = fields.Char(
        string='Configuración', required=True,
        default=lambda self: _('IA nativa de Odoo para Chatroom'))
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', string='Empresa', required=True,
        default=lambda self: self.env.company, index=True)
    native_agent_id = fields.Many2one(
        'ai.agent', string='Agente nativo de Odoo', ondelete='set null',
        help='Agente de la aplicación IA de Odoo que usará este puente.')
    native_agent_model = fields.Selection(
        related='native_agent_id.llm_model', string='Modelo nativo', readonly=True)
    native_agent_topics = fields.Many2many(
        related='native_agent_id.topic_ids', string='Temas del agente', readonly=True)
    use_for_knowledge = fields.Boolean(
        string='Usar para analizar conocimiento', default=True,
        help='Permite consultar el agente nativo para organizar y revisar conocimiento interno.')
    use_for_laboratory = fields.Boolean(
        string='Usar en el laboratorio IA', default=True,
        help='Habilita una prueba controlada con datos de Chatroom. No envía WhatsApp.')
    use_as_optional_backend = fields.Boolean(
        string='Disponible como motor opcional', default=False,
        help='Deja registrada la preferencia para el futuro adaptador conversacional. '
             'El núcleo OpenAI no se reemplaza automáticamente.')
    system_instructions = fields.Text(
        string='Instrucciones adicionales',
        default=lambda self: _(
            'Responde en español claro y profesional. Usa únicamente datos verificables '
            'de Odoo y del contexto entregado. Si falta información, dilo y solicita revisión humana.'))
    source_attachment_ids = fields.Many2many(
        'ir.attachment', 'chatroom_ai_odoo_bridge_attachment_rel',
        'bridge_id', 'attachment_id', string='Archivos para el agente nativo',
        help='PDF, documentos o archivos que se copiarán como fuentes del agente nativo.')
    state = fields.Selection([
        ('not_configured', 'Sin configurar'),
        ('ready', 'Listo'),
        ('error', 'Con error'),
    ], string='Estado', compute='_compute_state', store=True)
    status_message = fields.Char(string='Estado de la integración', compute='_compute_state', store=True)
    last_test_question = fields.Text(string='Última pregunta probada', readonly=True)
    last_test_answer = fields.Text(string='Última respuesta nativa', readonly=True)
    last_tested_at = fields.Datetime(string='Última prueba', readonly=True)
    last_error = fields.Text(string='Último error', readonly=True)
    native_source_count = fields.Integer(
        string='Fuentes nativas', compute='_compute_native_source_count')
    local_knowledge_preview = fields.Text(
        string='Contexto local enviado', readonly=True,
        help='Muestra el contexto resumido que Chatroom entrega al agente nativo.')
    test_question = fields.Text(
        string='Pregunta de prueba',
        default=lambda self: _(
            '¿Qué productos y servicios puede ofrecer nuestra empresa y cómo debo solicitar una cotización?'))

    _company_unique = models.Constraint(
        'unique(company_id)',
        'Solo puede existir una configuración del puente por empresa.')

    @api.depends('active', 'native_agent_id', 'native_agent_id.active')
    def _compute_state(self):
        for record in self:
            if not record.active:
                record.state = 'not_configured'
                record.status_message = _('Integración desactivada.')
            elif record.native_agent_id and record.native_agent_id.active:
                record.state = 'ready'
                record.status_message = _('Agente nativo disponible para pruebas y conocimiento.')
            else:
                record.state = 'not_configured'
                record.status_message = _('Crea o selecciona un agente nativo para comenzar.')

    def _compute_native_source_count(self):
        Source = self.env['ai.agent.source']
        for record in self:
            record.native_source_count = (
                Source.search_count([('agent_id', '=', record.native_agent_id.id)])
                if record.native_agent_id else 0)

    @api.model
    def _get_or_create_configuration(self):
        record = self.search([('company_id', '=', self.env.company.id)], limit=1)
        return record or self.create({'company_id': self.env.company.id})

    def _local_context(self, question):
        self.ensure_one()
        if 'ai.knowledge.base' not in self.env:
            return ''
        try:
            details = self.env['ai.knowledge.base'].sudo().get_sales_context_details(
                query=question or '', company=self.company_id)
        except Exception as error:
            _logger.warning('No se pudo cargar el contexto de Chatroom: %s', error)
            return ''
        return (details or {}).get('context', '') if isinstance(details, dict) else ''

    def action_create_native_agent(self):
        self.ensure_one()
        if self.native_agent_id:
            return self.action_open_native_agent()
        values = {
            'name': _('Agente comercial de Chatroom'),
            'subtitle': _('Agente nativo conectado a Chatroom'),
            'system_prompt': self.system_instructions,
            'response_style': 'balanced',
            'llm_model': 'gpt-4o',
            'restrict_to_sources': False,
        }
        try:
            agent = self.env['ai.agent'].create(values)
        except Exception as error:
            raise UserError(_(
                'No se pudo crear el agente nativo. Revisa la configuración de la aplicación IA de Odoo: %s'
            ) % error) from error
        self.native_agent_id = agent.id
        self.message_post(body=_('Agente nativo de Odoo creado y vinculado a esta configuración.'))
        return self.action_open_native_agent()

    def action_open_native_agent(self):
        self.ensure_one()
        if not self.native_agent_id:
            raise UserError(_('Primero crea o selecciona un agente nativo.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Agente nativo de Odoo'),
            'res_model': 'ai.agent',
            'res_id': self.native_agent_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_sync_sources(self):
        self.ensure_one()
        if not self.native_agent_id:
            raise UserError(_('Primero crea o selecciona un agente nativo.'))
        if not self.source_attachment_ids:
            raise UserError(_('Selecciona al menos un archivo para sincronizarlo como fuente.'))
        try:
            sources = self.env['ai.agent.source'].create_from_attachments(
                self.source_attachment_ids.ids, self.native_agent_id.id)
        except Exception as error:
            raise UserError(_(
                'No se pudieron registrar las fuentes en la IA nativa: %s'
            ) % error) from error
        self.message_post(body=_('Se enviaron %s archivo(s) al agente nativo. Odoo continuará su indexación en segundo plano.') % len(sources))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Fuentes registradas'),
                'message': _('Se registraron %s archivo(s). Revisa el estado de indexación en el agente nativo.') % len(sources),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_test_native(self):
        self.ensure_one()
        if not self.use_for_laboratory:
            raise UserError(_('Activa «Usar en el laboratorio IA» para ejecutar esta prueba.'))
        if not self.native_agent_id or not self.native_agent_id.active:
            raise UserError(_('Primero crea o selecciona un agente nativo activo.'))
        question = (self.test_question or '').strip()
        if not question:
            raise UserError(_('Escribe una pregunta de prueba.'))
        knowledge_context = self._local_context(question)
        context_message = self.system_instructions or ''
        if knowledge_context:
            context_message += _(
                '\n\nCONTEXTO AUTORIZADO DE CHATROOM:\n%s\n\n'
                'Usa estos datos como complemento y no inventes información fuera de ellos.'
            ) % knowledge_context
        try:
            response = self.native_agent_id.get_direct_response(
                question, context_message=context_message, enable_html_response=False)
            answer = '\n\n'.join(str(item) for item in (response or []))
        except Exception as error:
            self.write({
                'last_test_question': question,
                'last_error': str(error),
                'last_tested_at': fields.Datetime.now(),
            })
            raise UserError(_('La prueba de IA nativa falló: %s') % error) from error
        self.write({
            'last_test_question': question,
            'last_test_answer': answer or _('El agente no devolvió una respuesta.'),
            'local_knowledge_preview': knowledge_context,
            'last_error': False,
            'last_tested_at': fields.Datetime.now(),
        })
        self.message_post(body=_('Prueba nativa completada. No se envió ningún mensaje a WhatsApp.'))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Prueba completada'),
                'message': _('La respuesta quedó guardada en esta configuración. No se envió al cliente.'),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_prepare_optional_backend(self):
        self.ensure_one()
        if not self.native_agent_id:
            raise UserError(_('Primero crea o selecciona un agente nativo.'))
        self.use_as_optional_backend = True
        self.message_post(body=_(
            'La IA nativa quedó marcada como motor opcional. El motor actual de Chatroom permanece activo; '
            'el cambio conversacional se hará mediante un adaptador explícito y reversible.'))
        return True

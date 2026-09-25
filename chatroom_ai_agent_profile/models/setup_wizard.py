# -*- coding: utf-8 -*-
"""Asistente de puesta en marcha: de cero a un agente que responde, en 4 pasos."""
from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .agent_profile import TONES
from .ai_center import AUTONOMY_MODES
from .business_templates import TEMPLATES, template_selection

STEPS = [('company', '1. Empresa'), ('knowledge', '2. Información'), ('playbooks', '3. Guiones'),
         ('launch', '4. Probar y activar')]


class ChatroomAiAgentSetup(models.TransientModel):
    _name = 'chatroom.ai.agent.setup'
    _description = 'Puesta en marcha del agente IA'

    step = fields.Selection(STEPS, default='company', required=True)
    profile_id = fields.Many2one('chatroom.ai.agent.profile', required=True,
                                 default=lambda self: self.env['chatroom.ai.agent.profile']._for_line())
    # 1. Empresa
    company_name = fields.Char(string='Nombre de la empresa', default=lambda self: self.env.company.name)
    agent_name = fields.Char(string='Nombre del agente')
    tone = fields.Selection(TONES, string='Tono')
    business_description = fields.Text(string='¿A qué se dedica la empresa?')
    business_template = fields.Selection(
        template_selection(), string='Tipo de negocio',
        help='Llena el rol, los guiones con sus botones y la lista de información que conviene cargar. '
             'Todo queda editable.')
    # 2. Información
    knowledge_text = fields.Text(
        string='Información para responder',
        help='Horarios, envíos, formas de pago, políticas, preguntas frecuentes... separados por líneas en blanco.')
    knowledge_file = fields.Binary(string='O un PDF')
    knowledge_filename = fields.Char()
    knowledge_count = fields.Integer(compute='_compute_counts', string='Información publicada')
    # 3. Guiones
    use_quote = fields.Boolean(string='Reunir datos para cotizar o vender', default=True)
    quote_action = fields.Selection([
        ('handoff', 'Pasar a una persona con los datos'),
        ('quote', 'Preparar cotización en borrador y pasar a una persona'),
        ('lead', 'Crear oportunidad en CRM y seguir'),
    ], string='Al tener los datos', default='handoff')
    use_support = fields.Boolean(string='Reunir datos de un problema (soporte)', default=True)
    template_playbooks = fields.Text(compute='_compute_template_playbooks', string='Guiones de la plantilla')
    autonomy_mode = fields.Selection(AUTONOMY_MODES, string='¿Cuánto decide sola la IA?', default='balanced')
    # 4. Resultado
    readiness_html = fields.Html(related='profile_id.readiness_html')
    auto_reply_on = fields.Boolean(related='profile_id.auto_reply_on')

    @api.depends('profile_id')
    def _compute_counts(self):
        count = self.env['ai.knowledge.base'].sudo().search_count([
            ('publication_state', '=', 'published'), ('state', '=', 'indexed')])
        for wizard in self:
            wizard.knowledge_count = count

    @api.depends('business_template', 'profile_id')
    def _compute_template_playbooks(self):
        labels = dict(self.env['chatroom.ai.agent.playbook']._fields['on_complete'].selection)
        for wizard in self:
            data = TEMPLATES.get(wizard.business_template)
            wizard.template_playbooks = '\n'.join(
                '• %s (%s): %s → %s' % (name, ', '.join(row[0] for row in rows), when, labels.get(action, action))
                for _code, name, when, action, rows in data['playbooks']) if data else False

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        profile = self.env['chatroom.ai.agent.profile'].browse(values.get('profile_id'))
        if profile:
            values.setdefault('agent_name', profile.agent_name)
            values.setdefault('tone', profile.tone)
            values.setdefault('business_description', profile.business_description)
            values.setdefault('business_template', profile.business_template)
            values.setdefault('autonomy_mode', profile.autonomy_mode)
            quote = self.env.ref('chatroom_ai_agent_profile.playbook_quote', raise_if_not_found=False)
            support = self.env.ref('chatroom_ai_agent_profile.playbook_support', raise_if_not_found=False)
            if quote and quote.profile_id == profile:
                values.setdefault('use_quote', quote.active)
                if quote.on_complete in ('handoff', 'quote', 'lead'):
                    values.setdefault('quote_action', quote.on_complete)
            if support and support.profile_id == profile:
                values.setdefault('use_support', support.active)
        return values

    def _reopen(self):
        return {'type': 'ir.actions.act_window', 'name': _('Puesta en marcha del agente'), 'res_model': self._name,
                'res_id': self.id, 'view_mode': 'form', 'views': [(False, 'form')], 'target': 'new',
                'context': {'dialog_size': 'large'}}

    # ------------------------------------------------------------------
    def _save_company(self):
        if not (self.business_description or '').strip():
            raise UserError(_('Cuéntale al agente a qué se dedica la empresa: se presenta y responde con eso.'))
        if self.company_name and self.company_name != self.env.company.name:
            self.env.company.sudo().name = self.company_name
        self.profile_id.write({'agent_name': self.agent_name or self.profile_id.agent_name,
                               'tone': self.tone or self.profile_id.tone,
                               'business_description': self.business_description.strip()})
        if self.business_template and self.business_template != self.profile_id.business_template:
            self.profile_id.action_apply_template(self.business_template)

    def _save_knowledge(self):
        Knowledge = self.env['ai.knowledge.base'].sudo()
        created = Knowledge.browse()
        if (self.knowledge_text or '').strip():
            created |= Knowledge.create({'name': _('Información general (puesta en marcha)'), 'source_type': 'text',
                                         'source_text': self.knowledge_text.strip()})
        if self.knowledge_file:
            created |= Knowledge.create({'name': self.knowledge_filename or _('Documento'), 'source_type': 'pdf',
                                         'pdf_file': self.knowledge_file, 'pdf_filename': self.knowledge_filename})
        for record in created:
            record.action_index()
            if record.state != 'indexed':
                raise UserError(_('No se pudo leer «%(name)s»: %(error)s') % {
                    'name': record.name, 'error': record.processing_error or _('sin texto')})
            record.action_publish()
        if not created and not self.knowledge_count:
            raise UserError(_('Escribe la información o sube un PDF: sin información el agente no puede responder.'))
        self.write({'knowledge_text': False, 'knowledge_file': False, 'knowledge_filename': False})

    def _save_playbooks(self):
        if self.business_template:
            return  # los guiones vienen de la plantilla y se ajustan en el perfil
        quote = self.env.ref('chatroom_ai_agent_profile.playbook_quote', raise_if_not_found=False)
        support = self.env.ref('chatroom_ai_agent_profile.playbook_support', raise_if_not_found=False)
        if quote and quote.profile_id == self.profile_id:
            quote.write({'active': self.use_quote, 'on_complete': self.quote_action or 'handoff'})
        if support and support.profile_id == self.profile_id:
            support.write({'active': self.use_support})

    def action_next(self):
        self.ensure_one()
        order = [key for key, _label in STEPS]
        {'company': self._save_company, 'knowledge': self._save_knowledge,
         'playbooks': self._save_playbooks}.get(self.step, lambda: None)()
        self.step = order[min(order.index(self.step) + 1, len(order) - 1)]
        return self._reopen()

    def action_back(self):
        self.ensure_one()
        order = [key for key, _label in STEPS]
        self.step = order[max(order.index(self.step) - 1, 0)]
        return self._reopen()

    def action_test(self):
        return self.profile_id.action_open_simulator()

    def action_activate(self):
        self.profile_id.write({'autonomy_mode': self.autonomy_mode or 'balanced'})
        self.profile_id.action_enable_auto_reply()
        return {'type': 'ir.actions.act_window', 'res_model': 'chatroom.ai.agent.profile',
                'res_id': self.profile_id.id, 'view_mode': 'form', 'views': [(False, 'form')], 'target': 'current'}

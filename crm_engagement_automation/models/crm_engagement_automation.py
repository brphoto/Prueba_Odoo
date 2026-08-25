# -*- coding: utf-8 -*-
from datetime import date, timedelta
import calendar
import json
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class CrmEngagementAutomation(models.Model):
    _name = 'crm.engagement.automation'
    _description = 'Automatización comercial'
    _inherit = ['mail.thread']
    _order = 'active desc, sequence, name'

    name = fields.Char(string='Nombre', required=True, tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=False, tracking=True)
    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True,
        default=lambda self: self.env.company, index=True)
    source_type = fields.Selection([
        ('birthday', 'Cumpleaños del cliente'),
        ('invoice_due', 'Factura por vencer'),
        ('opportunity_deadline', 'Fecha límite de oportunidad'),
        ('last_purchase_anniversary', 'Aniversario de última compra'),
        ('custom_event', 'Evento personalizado'),
    ], string='Disparador', required=True, default='custom_event', tracking=True)
    only_customers = fields.Boolean(
        string='Solo clientes', default=False,
        help='Si está activo, excluye contactos que todavía no tienen historial como cliente.')
    rfm_category_ids = fields.Many2many(
        'crm.rfm.segment', 'crm_engagement_rfm_rel', 'automation_id', 'segment_id',
        string='Categorías RFM',
        domain=[('definition_type', '=', 'category'), ('active', '=', True)],
        help='Vacío significa todas las categorías.')
    tag_ids = fields.Many2many(
        'res.partner.category', 'crm_engagement_tag_rel', 'automation_id', 'tag_id',
        string='Etiquetas de cliente', help='El cliente debe tener al menos una etiqueta seleccionada.')
    step_ids = fields.One2many(
        'crm.engagement.automation.step', 'automation_id', string='Recordatorios', copy=True)
    last_run = fields.Datetime(string='Última ejecución', readonly=True, copy=False)
    last_preview_count = fields.Integer(string='Último resultado', readonly=True, copy=False)

    preview_text = fields.Text(
        string='Ejemplos de mensajes', readonly=True, copy=False,
        help='Muestra ejemplos con las variables sustituidas antes de activar la automatizacion.')

    def _get_target_partners(self):
        self.ensure_one()
        domain = [
            ('active', '=', True),
            '|', ('company_id', '=', self.company_id.id), ('company_id', '=', False),
        ]
        if self.only_customers:
            domain.append(('customer_rank', '>', 0))
        if self.rfm_category_ids:
            domain.append(('rfm_category', 'in', self.rfm_category_ids.mapped('code')))
        if self.tag_ids:
            domain.append(('category_id', 'in', self.tag_ids.ids))
        return self.env['res.partner'].search(domain)

    @staticmethod
    def _birthday_date(birthday, year):
        if not birthday:
            return False
        if birthday.month == 2 and birthday.day == 29 and not calendar.isleap(year):
            return date(year, 2, 28)
        return date(year, birthday.month, birthday.day)

    def _base_context(self, partner, event_name, event_date, today, extra=None):
        self.ensure_one()
        values = {
            'partner_name': partner.name or '',
            'first_name': (partner.name or '').split(' ')[0],
            'event_name': event_name or '',
            'event_date': fields.Date.to_string(event_date) if event_date else '',
            'days_to_event': (event_date - today).days if event_date else '',
            'rfm_category': getattr(partner, 'rfm_category', '') or '',
            'rfm_score': getattr(partner, 'rfm_score', 0) or 0,
            'phone': partner.phone or '',
            'email': partner.email or '',
            'engagement_note': getattr(partner, 'engagement_note', '') or '',
        }
        values.update(extra or {})
        return values

    def _candidate_events(self, step, today):
        self.ensure_one()
        event_date = today - timedelta(days=step.days_offset)
        partners = self._get_target_partners()
        candidates = []
        if self.source_type == 'birthday':
            for partner in partners.filtered('engagement_birthday'):
                birthday = self._birthday_date(partner.engagement_birthday, event_date.year)
                if birthday == event_date:
                    candidates.append({
                        'partner': partner, 'event_date': birthday,
                        'event_name': 'Cumpleaños',
                        'event_key': 'birthday:%s' % event_date.year,
                        'context': self._base_context(partner, 'Cumpleaños', birthday, today),
                    })
        elif self.source_type == 'last_purchase_anniversary':
            for partner in partners.filtered('commercial_last_sale_date'):
                anniversary = self._birthday_date(partner.commercial_last_sale_date, event_date.year)
                if anniversary == event_date:
                    candidates.append({
                        'partner': partner, 'event_date': anniversary,
                        'event_name': 'Aniversario de última compra',
                        'event_key': 'purchase_anniversary:%s' % event_date.year,
                        'context': self._base_context(partner, 'Aniversario de última compra', anniversary, today),
                    })
        elif self.source_type == 'custom_event':
            events = self.env['crm.engagement.event'].search([
                ('active', '=', True),
                '|', ('company_id', '=', self.company_id.id), ('company_id', '=', False),
                ('event_date', '=', event_date), ('partner_id', 'in', partners.ids),
            ])
            for event in events:
                candidates.append({
                    'partner': event.partner_id, 'event_date': event.event_date,
                    'event_name': event.name, 'event_key': 'event:%s' % event.id,
                    'context': self._base_context(event.partner_id, event.name, event.event_date, today, {
                        'event_description': event.description or '',
                        'event_type': dict(event._fields['event_type'].selection).get(event.event_type, ''),
                    }),
                })
        elif self.source_type == 'invoice_due':
            invoices = self.env['account.move'].search([
                ('move_type', '=', 'out_invoice'), ('state', '=', 'posted'),
                ('payment_state', 'not in', ('paid', 'reversed')), 
                ('invoice_date_due', '=', event_date),
                ('partner_id', 'in', partners.ids),
                ('company_id', '=', self.company_id.id),
            ])
            for invoice in invoices:
                partner = invoice.partner_id
                candidates.append({
                    'partner': partner, 'event_date': invoice.invoice_date_due,
                    'event_name': 'Vencimiento de factura %s' % (invoice.name or invoice.id),
                    'event_key': 'invoice:%s' % invoice.id,
                    'context': self._base_context(partner, 'Vencimiento de factura', invoice.invoice_date_due, today, {
                        'invoice_number': invoice.name or '',
                        'invoice_amount': invoice.amount_residual or invoice.amount_total or 0,
                    }),
                })
        elif self.source_type == 'opportunity_deadline':
            Lead = self.env['crm.lead']
            if 'date_deadline' not in Lead._fields:
                return candidates
            leads = Lead.search([
                ('active', '=', True), ('type', '=', 'opportunity'),
                ('stage_id.is_won', '=', False), ('date_deadline', '=', event_date),
                ('partner_id', 'in', partners.ids), ('company_id', '=', self.company_id.id),
            ])
            for lead in leads:
                partner = lead.partner_id
                candidates.append({
                    'partner': partner, 'event_date': lead.date_deadline,
                    'event_name': 'Fecha límite de oportunidad',
                    'event_key': 'lead:%s' % lead.id,
                    'context': self._base_context(partner, 'Fecha límite de oportunidad', lead.date_deadline, today, {
                        'lead_name': lead.name or '',
                        'expected_revenue': lead.expected_revenue or 0,
                    }),
                })
        return candidates

    def _process(self, today=None, execute=True):
        self.ensure_one()
        today = today or fields.Date.context_today(self)
        created = 0
        for step in self.step_ids.sorted('sequence'):
            for candidate in self._candidate_events(step, today):
                existing = self.env['crm.engagement.execution'].search_count([
                    ('automation_id', '=', self.id), ('step_id', '=', step.id),
                    ('partner_id', '=', candidate['partner'].id),
                    ('event_key', '=', candidate['event_key']),
                ])
                if existing:
                    continue
                execution = self.env['crm.engagement.execution'].create({
                    'automation_id': self.id, 'step_id': step.id,
                    'partner_id': candidate['partner'].id,
                    'event_key': candidate['event_key'],
                    'event_name': candidate['event_name'],
                    'event_date': candidate['event_date'], 'scheduled_date': today,
                    'state': 'pending_approval' if step.requires_approval else 'queued',
                    'context_json': json.dumps(candidate['context'], ensure_ascii=False),
                })
                created += 1
                if execute and not step.requires_approval:
                    execution.action_execute()
        self.write({'last_run': fields.Datetime.now(), 'last_preview_count': created})
        return created

    def action_preview(self):
        self.ensure_one()
        count = 0
        examples = []
        today = fields.Date.context_today(self)
        execution_model = self.env['crm.engagement.execution']
        for step in self.step_ids.sorted('sequence'):
            candidates = self._candidate_events(step, today)
            count += len(candidates)
            for candidate in candidates[:10 - len(examples)]:
                rendered = execution_model._render_message(
                    step.message_body, candidate.get('context', {}))
                examples.append('%s | %s\n%s' % (
                    candidate['partner'].display_name, step.name, rendered))
                if len(examples) >= 10:
                    break
            if len(examples) >= 10:
                break
        preview = '\n\n'.join(examples) if examples else _(
            'No hay clientes o eventos que cumplan la regla para hoy.')
        self.write({'last_preview_count': count, 'preview_text': preview})
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'title': _('Previsualización de automatización'),
                'message': _('%s recordatorio(s) cumplen las reglas para hoy.') % count,
                'type': 'success' if count else 'info', 'sticky': False,
            },
        }

    def action_run_now(self):
        self.ensure_one()
        if not self.env.user.has_group('crm_engagement_automation.group_crm_engagement_manager'):
            raise UserError(_('Solo un administrador puede ejecutar automatizaciones manualmente.'))
        created = self._process()
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'title': _('Automatización ejecutada'),
                'message': _('%s recordatorio(s) fueron procesados.') % created,
                'type': 'success', 'sticky': False,
            },
        }

    @api.model
    def _cron_process_engagement_automations(self):
        total = 0
        for automation in self.search([('active', '=', True)]):
            total += automation._process()
        return total


class CrmEngagementAutomationStep(models.Model):
    _name = 'crm.engagement.automation.step'
    _description = 'Recordatorio de automatización comercial'
    _order = 'sequence, id'

    automation_id = fields.Many2one(
        'crm.engagement.automation', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    name = fields.Char(string='Nombre', required=True, default='Recordatorio')
    days_offset = fields.Integer(
        string='Días respecto al evento', default=-7, required=True,
        help='Use -7 para avisar 7 días antes, 0 el mismo día o 2 dos días después.')
    channel = fields.Selection([
        ('activity', 'Actividad de Odoo'),
        ('notification', 'Notificación interna'),
        ('email', 'Correo electrónico'),
        ('whatsapp', 'WhatsApp (plantilla aprobada)'),
    ], string='Canal', default='activity', required=True)
    requires_approval = fields.Boolean(
        string='Requiere aprobación', default=False,
        help='Deja el envío pendiente para que un administrador lo apruebe manualmente.')
    message_body = fields.Text(
        string='Mensaje personalizado', required=True,
        default='Hola ${first_name}, te recordamos: ${event_name} el ${event_date}.')
    variable_to_insert = fields.Selection(
        selection=[
            ('partner_name', 'Nombre completo del cliente'),
            ('first_name', 'Primer nombre'),
            ('event_name', 'Nombre del evento'),
            ('event_date', 'Fecha del evento'),
            ('days_to_event', 'Días hasta el evento'),
            ('rfm_category', 'Categoría del cliente'),
            ('rfm_score', 'Puntaje del cliente'),
            ('phone', 'Teléfono'),
            ('email', 'Correo electrónico'),
            ('engagement_note', 'Nota comercial'),
            ('event_description', 'Detalle del evento'),
            ('invoice_number', 'Número de factura'),
            ('invoice_amount', 'Saldo de factura'),
            ('lead_name', 'Nombre de oportunidad'),
            ('expected_revenue', 'Ingreso esperado'),
        ],
        string='Agregar dato al mensaje',
        help='Selecciona un dato y se agregará automáticamente al final del mensaje.')
    message_preview = fields.Text(
        string='Vista previa con datos de ejemplo', compute='_compute_message_preview')
    activity_summary = fields.Char(string='Resumen de actividad', default='Recordatorio comercial')
    activity_type_id = fields.Many2one('mail.activity.type', string='Tipo de actividad')
    user_id = fields.Many2one('res.users', string='Asignar actividad a')
    email_subject = fields.Char(string='Asunto del correo', default='Recordatorio para ${partner_name}')
    mail_template_id = fields.Many2one(
        'mail.template', string='Plantilla de correo',
        domain=[('model_id.model', '=', 'res.partner')])
    whatsapp_template_name = fields.Char(
        string='Nombre de plantilla WhatsApp',
        help='Debe coincidir con una plantilla aprobada sincronizada desde Meta.')
    whatsapp_template_language = fields.Char(string='Idioma WhatsApp', default='es')

    @api.model
    def _message_variables(self):
        return {
            'partner_name', 'first_name', 'event_name', 'event_date',
            'days_to_event', 'rfm_category', 'rfm_score', 'phone', 'email',
            'engagement_note', 'event_description', 'invoice_number',
            'invoice_amount', 'lead_name', 'expected_revenue',
        }

    @api.onchange('variable_to_insert')
    def _onchange_variable_to_insert(self):
        for step in self:
            if not step.variable_to_insert:
                continue
            token = '${%s}' % step.variable_to_insert
            current = (step.message_body or '').rstrip()
            step.message_body = '%s %s' % (current, token) if current else token
            step.variable_to_insert = False

    @api.depends('message_body')
    def _compute_message_preview(self):
        examples = {
            '${partner_name}': 'María González',
            '${first_name}': 'María',
            '${event_name}': 'Renovación de plan',
            '${event_date}': '31/08/2026',
            '${days_to_event}': '7',
            '${rfm_category}': 'A - Alto valor',
            '${rfm_score}': '92',
            '${phone}': '+593 999 000 000',
            '${email}': 'maria@example.com',
            '${engagement_note}': 'Cliente preferente',
            '${event_description}': 'Revisar propuesta anual',
            '${invoice_number}': 'FAC-000123',
            '${invoice_amount}': '250,00',
            '${lead_name}': 'Renovación corporativa',
            '${expected_revenue}': '1.500,00',
        }
        for step in self:
            preview = step.message_body or ''
            for token, example in examples.items():
                preview = preview.replace(token, example)
            step.message_preview = preview

    @api.constrains('channel', 'message_body', 'days_offset')
    def _check_step(self):
        for step in self:
            if not step.message_body and step.channel != 'whatsapp':
                raise ValidationError(_('El mensaje personalizado no puede quedar vacío.'))
            if step.channel == 'whatsapp' and not step.whatsapp_template_name:
                raise ValidationError(_('Indica el nombre de la plantilla aprobada de WhatsApp.'))
            tokens = set(re.findall(r'\$\{([a-zA-Z0-9_]+)\}', step.message_body or ''))
            unknown = sorted(tokens - step._message_variables())
            if unknown:
                raise ValidationError(_(
                    'El mensaje contiene variables no disponibles: %s. '
                    'Usa el selector "Agregar dato al mensaje".') % ', '.join(
                        '${%s}' % token for token in unknown))

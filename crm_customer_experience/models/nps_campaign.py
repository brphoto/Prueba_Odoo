# -*- coding: utf-8 -*-
"""Campañas NPS segmentadas.

La campaña vive en Experiencia del cliente y solo conoce el resultado que
necesita: una audiencia RFM y un enlace de encuesta. Los conectores de canal
(por ejemplo WhatsApp) implementan el envío en módulos opcionales.
"""
import html
import logging
from urllib.parse import quote

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class CrmNpsCampaign(models.Model):
    _name = 'crm.nps.campaign'
    _description = 'Campaña de encuesta NPS'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc, id desc'

    name = fields.Char(string='Nombre de la campaña', required=True, tracking=True)
    survey_id = fields.Many2one(
        'survey.survey', string='Encuesta', required=True,
        default=lambda self: self.env.ref('crm_customer_experience.survey_nps', raise_if_not_found=False),
        domain=[('active', '=', True)], ondelete='restrict')
    target_category_ids = fields.Many2many(
        'crm.rfm.segment', 'crm_nps_campaign_rfm_category_rel',
        'campaign_id', 'category_id', string='Categorías RFM objetivo',
        domain=[('definition_type', '=', 'category'), ('active', '=', True)],
        help='Selecciona A, B, C o cualquier categoría personalizada del catálogo RFM.')
    target_segment_ids = fields.Many2many(
        'crm.rfm.segment', 'crm_nps_campaign_rfm_segment_rel',
        'campaign_id', 'segment_id', string='Segmentos RFM guardados',
        domain=[('definition_type', '=', 'segment'), ('active', '=', True)],
        help='Opcionalmente combina las categorías con segmentos que tengan reglas visuales.')
    channel = fields.Selection(
        [('email', 'Correo electrónico')], string='Canal', default='email', required=True,
        tracking=True,
        help='WhatsApp y Correo y WhatsApp aparecen al instalar el conector opcional de Chatroom.')
    email_subject = fields.Char(
        string='Asunto del correo', default='¿Cómo fue tu experiencia con nosotros?')
    email_body = fields.Text(
        string='Mensaje del correo', default=(
            '<p>Hola {{name}},</p>'
            '<p>Nos gustaría conocer tu opinión. Responder solo te tomará un momento:</p>'
            '<p><a href="{{link}}">Responder encuesta NPS</a></p>'
            '<p>Gracias por ayudarnos a mejorar.</p>'),
        help='Puedes usar {{name}}, {{link}}, {{rfm_category}} y {{rfm_score}}.')
    exclude_answered_days = fields.Integer(
        string='No repetir durante (días)', default=90,
        help='Evita enviar otra encuesta a clientes que ya respondieron NPS durante este período. Usa 0 para no excluir.')
    batch_size = fields.Integer(string='Tamaño de lote', default=20, required=True)
    state = fields.Selection([
        ('draft', 'Borrador'), ('queued', 'En cola'), ('processing', 'Procesando'),
        ('done', 'Completada'), ('cancelled', 'Cancelada'),
    ], string='Estado', default='draft', required=True, copy=False, tracking=True)
    recipient_ids = fields.One2many('crm.nps.campaign.recipient', 'campaign_id', string='Destinatarios')
    recipient_count = fields.Integer(string='Destinatarios', compute='_compute_stats')
    pending_count = fields.Integer(string='Pendientes', compute='_compute_stats')
    sent_count = fields.Integer(string='Enviados', compute='_compute_stats')
    failed_count = fields.Integer(string='Fallidos', compute='_compute_stats')
    skipped_count = fields.Integer(string='Omitidos', compute='_compute_stats')
    audience_count = fields.Integer(string='Audiencia actual', compute='_compute_audience_count')
    queued_date = fields.Datetime(string='Encolada el', readonly=True, copy=False)
    completed_date = fields.Datetime(string='Completada el', readonly=True, copy=False)
    last_run = fields.Datetime(string='Último procesamiento', readonly=True, copy=False)
    last_error = fields.Text(string='Último error', readonly=True, copy=False)

    @api.depends('recipient_ids.email_state', 'recipient_ids.whatsapp_state', 'recipient_ids.state', 'state')
    def _compute_stats(self):
        for campaign in self:
            lines = campaign.recipient_ids
            campaign.recipient_count = len(lines)
            campaign.pending_count = len(lines.filtered(lambda line: line.state == 'pending'))
            campaign.sent_count = len(lines.filtered(lambda line: line.state == 'sent'))
            campaign.failed_count = len(lines.filtered(lambda line: line.state == 'failed'))
            campaign.skipped_count = len(lines.filtered(lambda line: line.state == 'skipped'))

    @api.depends('target_category_ids', 'target_segment_ids', 'exclude_answered_days')
    def _compute_audience_count(self):
        for campaign in self:
            campaign.audience_count = len(campaign._get_target_partners())

    @api.constrains('batch_size', 'exclude_answered_days')
    def _check_campaign_numbers(self):
        for campaign in self:
            if campaign.batch_size < 1:
                raise ValidationError(_('El tamaño de lote debe ser mayor que cero.'))
            if campaign.exclude_answered_days < 0:
                raise ValidationError(_('Los días para no repetir no pueden ser negativos.'))

    @api.constrains('target_category_ids', 'target_segment_ids')
    def _check_audience(self):
        for campaign in self:
            if not campaign.target_category_ids and not campaign.target_segment_ids:
                raise ValidationError(_('Selecciona al menos una categoría o segmento RFM objetivo.'))

    def _get_target_partners(self):
        self.ensure_one()
        partners = self.env['res.partner']
        if self.target_category_ids:
            partners |= self.env['res.partner'].search([
                ('rfm_category', 'in', self.target_category_ids.mapped('code')),
                ('customer_rank', '>', 0),
            ])
        for segment in self.target_segment_ids:
            partners |= segment.get_matching_partners()
        if self.exclude_answered_days:
            cutoff = fields.Date.subtract(fields.Date.context_today(self), days=self.exclude_answered_days)
            answered_partner_ids = self.env['crm.nps.response'].search([
                ('response_date', '>=', cutoff), ('partner_id', '!=', False),
            ]).mapped('partner_id').ids
            if answered_partner_ids:
                partners = partners.filtered(lambda partner: partner.id not in answered_partner_ids)
        return partners.sorted(key=lambda partner: (partner.name or '').lower())

    def _requested_channels(self):
        self.ensure_one()
        return ['email']

    def _make_survey_answer(self, partner):
        self.ensure_one()
        survey = self.survey_id.sudo()
        answer = survey._create_answer(partner=partner.sudo(), check_attempts=False)
        answer = answer[:1]
        base_url = (survey.get_base_url() or '').rstrip('/')
        url = '%s%s?answer_token=%s' % (
            base_url, survey.get_start_url(), quote(answer.access_token or '', safe=''))
        return answer, url

    def _render_message(self, line):
        self.ensure_one()
        partner = line.partner_id
        values = {
            'name': html.escape(partner.name or 'cliente'),
            'link': html.escape(line.survey_url or ''),
            'rfm_category': html.escape(partner.rfm_category or 'Sin historial'),
            'rfm_score': str(partner.rfm_score or 0),
        }
        subject = (self.email_subject or '').replace('{{name}}', values['name'])
        body = self.email_body or ''
        for key, value in values.items():
            body = body.replace('{{%s}}' % key, value)
        return subject, body

    def action_preview_audience(self):
        self.ensure_one()
        partners = self._get_target_partners()
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'title': _('Audiencia NPS'),
                'message': _('%s contacto(s) cumplen las categorías/segmentos seleccionados.') % len(partners),
                'type': 'success' if partners else 'warning',
                'sticky': False,
            },
        }

    def action_queue(self):
        for campaign in self:
            campaign.ensure_one()
            if campaign.state != 'draft':
                raise UserError(_('Solo se puede encolar una campaña en borrador.'))
            partners = campaign._get_target_partners()
            if not partners:
                raise UserError(_('No hay contactos que cumplan los filtros seleccionados.'))
            existing = set(campaign.recipient_ids.mapped('partner_id').ids)
            vals_list = []
            for partner in partners:
                if partner.id in existing:
                    continue
                try:
                    answer, url = campaign._make_survey_answer(partner)
                except Exception as exc:  # noqa: BLE001 - se deja trazabilidad por destinatario
                    _logger.exception('No se pudo preparar la encuesta para %s', partner.id)
                    vals_list.append({
                        'partner_id': partner.id, 'state': 'failed',
                        'email_state': 'failed', 'whatsapp_state': 'skipped',
                        'error_message': str(exc)[:500],
                    })
                    continue
                vals_list.append({
                    'partner_id': partner.id,
                    'survey_user_input_id': answer.id,
                    'survey_url': url,
                })
            if vals_list:
                campaign.env['crm.nps.campaign.recipient'].create([
                    dict(vals, campaign_id=campaign.id) for vals in vals_list])
            campaign.write({'state': 'queued', 'queued_date': fields.Datetime.now(), 'last_error': False})
            campaign.message_post(body=_(
                'Campaña encolada para %(count)s contacto(s). El procesamiento se hará por lotes de %(batch)s.'
            ) % {'count': len(vals_list), 'batch': campaign.batch_size})
        return True

    def action_process_now(self):
        for campaign in self:
            if campaign.state not in ('queued', 'processing'):
                raise UserError(_('La campaña debe estar en cola para procesarse.'))
            campaign._process_batch()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_cancel(self):
        self.filtered(lambda campaign: campaign.state in ('draft', 'queued', 'processing')).write({'state': 'cancelled'})
        return True

    def _send_email_recipient(self, line):
        if not line.partner_id.email:
            line.write({'email_state': 'skipped', 'error_message': _('El contacto no tiene correo electrónico.')})
            return
        subject, body = self._render_message(line)
        mail = self.env['mail.mail'].sudo().create({
            'subject': subject,
            'body_html': body,
            'email_to': line.partner_id.email,
            'recipient_ids': [(6, 0, [line.partner_id.id])],
            'auto_delete': False,
        })
        line.mail_id = mail.id
        mail.send(raise_exception=False)
        if mail.state == 'sent':
            line.write({'email_state': 'sent', 'sent_date': fields.Datetime.now(), 'error_message': False})
        else:
            line.write({'email_state': 'failed', 'error_message': mail.failure_reason or _('El correo quedó pendiente o falló.')})

    def _send_whatsapp_recipient(self, line):
        line.write({
            'whatsapp_state': 'skipped',
            'error_message': _('WhatsApp no está instalado para esta campaña.'),
        })

    def _process_batch(self):
        self.ensure_one()
        channels = self._requested_channels()
        self.write({'state': 'processing', 'last_run': fields.Datetime.now()})
        pending = self.recipient_ids.filtered(lambda line: line.state == 'pending')[:self.batch_size]
        for line in pending:
            try:
                if 'email' in channels and line.email_state == 'pending':
                    self._send_email_recipient(line)
                if 'whatsapp' in channels and line.whatsapp_state == 'pending':
                    self._send_whatsapp_recipient(line)
            except Exception as exc:  # noqa: BLE001 - un fallo individual no detiene la campaña
                _logger.exception('Error procesando destinatario NPS %s', line.id)
                line.write({'error_message': str(exc)[:500]})
                if 'email' in channels and line.email_state == 'pending':
                    line.email_state = 'failed'
                if 'whatsapp' in channels and line.whatsapp_state == 'pending':
                    line.whatsapp_state = 'failed'
        if not self.recipient_ids.filtered(lambda line: line.state == 'pending'):
            self.write({'state': 'done', 'completed_date': fields.Datetime.now()})

    @api.model
    def _cron_process_campaigns(self):
        for campaign in self.search([('state', 'in', ('queued', 'processing'))], order='id'):
            campaign._process_batch()
        return True


class CrmNpsCampaignRecipient(models.Model):
    _name = 'crm.nps.campaign.recipient'
    _description = 'Destinatario de campaña NPS'
    _order = 'id'

    campaign_id = fields.Many2one('crm.nps.campaign', required=True, ondelete='cascade', index=True)
    partner_id = fields.Many2one('res.partner', string='Cliente', required=True, ondelete='restrict', index=True)
    survey_user_input_id = fields.Many2one('survey.user_input', string='Respuesta pendiente', readonly=True, ondelete='set null')
    response_id = fields.Many2one('crm.nps.response', string='Respuesta NPS', readonly=True, ondelete='set null')
    survey_url = fields.Char(string='Enlace de encuesta', readonly=True, copy=False)
    email_state = fields.Selection([
        ('pending', 'Pendiente'), ('sent', 'Enviado'), ('failed', 'Fallido'), ('skipped', 'Omitido'),
    ], default='pending', required=True, copy=False)
    whatsapp_state = fields.Selection([
        ('pending', 'Pendiente'), ('sent', 'Enviado'), ('failed', 'Fallido'), ('skipped', 'Omitido'),
    ], default='pending', required=True, copy=False)
    mail_id = fields.Many2one('mail.mail', string='Correo enviado', readonly=True, ondelete='set null')
    sent_date = fields.Datetime(string='Enviado el', readonly=True, copy=False)
    error_message = fields.Char(string='Detalle', copy=False)
    state = fields.Selection([
        ('pending', 'Pendiente'), ('sent', 'Enviado'), ('failed', 'Fallido'), ('skipped', 'Omitido'),
    ], compute='_compute_state', string='Estado', store=True)

    @api.depends('email_state', 'whatsapp_state', 'campaign_id.channel')
    def _compute_state(self):
        for line in self:
            requested = line.campaign_id._requested_channels() if line.campaign_id else ['email']
            states = [getattr(line, '%s_state' % channel) for channel in requested]
            if any(state == 'pending' for state in states):
                line.state = 'pending'
            elif any(state == 'sent' for state in states):
                line.state = 'sent'
            elif any(state == 'failed' for state in states):
                line.state = 'failed'
            else:
                line.state = 'skipped'

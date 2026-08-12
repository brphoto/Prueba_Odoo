# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ChatroomCampaign(models.Model):
    """Envío masivo de una plantilla de WhatsApp (HSM) a los contactos de
    una o más categorías RFM (ej. reactivar la categoría C, agradecer a
    la A). Vive en este módulo -no en chatroom_whatsapp ni en
    crm_customer_intelligence- porque necesita los dos a la vez: la
    segmentación RFM y el canal de envío por WhatsApp.

    El envío en sí lo hace un cron en lotes (ver _cron_process_campaigns):
    mandar todo de una en un solo request, además de poder hacer timeout
    con segmentaciones grandes, ignora los límites de tasa de envío de la
    Cloud API de Meta."""
    _name = 'chatroom.campaign'
    _description = "Campaña de WhatsApp por categoría RFM"
    _inherit = ['mail.thread']
    _order = 'create_date desc'

    name = fields.Char(required=True)
    template_id = fields.Many2one(
        'chatroom.template', required=True, string="Plantilla",
        domain=[('status', '=', 'approved')],
        help="Solo plantillas aprobadas por Meta: es la única forma de "
             "escribirle primero a un cliente fuera de la ventana de 24h "
             "desde su último mensaje.")
    target_rfm_a = fields.Boolean(string="Categoría A (mejores clientes)", default=True)
    target_rfm_b = fields.Boolean(string="Categoría B (intermedios)")
    target_rfm_c = fields.Boolean(string="Categoría C (en riesgo/inactivos)")
    target_category_ids = fields.Many2many(
        'crm.rfm.category', 'chatroom_campaign_rfm_category_rel',
        'campaign_id', 'category_id', string='Categorías RFM',
        default=lambda self: self.env['crm.rfm.category'].search(
            [('code', '=', 'a'), ('active', '=', True)], limit=1),
        domain=[('active', '=', True)],
        help='Selecciona cualquier categoría del catálogo RFM, incluidas las personalizadas. '
             'Las casillas A/B/C se conservan para compatibilidad con campañas antiguas.',
    )
    segment_id = fields.Many2one(
        'crm.rfm.segment', string='Segmento guardado',
        domain=[('active', '=', True)],
        help='Usa las reglas visuales del segmento para seleccionar destinatarios.')
    batch_size = fields.Integer(
        default=20, required=True, string="Tamaño de lote",
        help="Cuántos mensajes manda cada corrida del cron (cada 5 "
             "minutos), para no pegarle de una a los límites de envío de "
             "la Cloud API de Meta ni hacer timeout en segmentaciones "
             "grandes.")
    state = fields.Selection(
        [('draft', "Borrador"), ('sending', "Enviando"), ('sent', "Enviada")],
        default='draft', required=True, copy=False)
    recipient_ids = fields.One2many('chatroom.campaign.recipient', 'campaign_id')
    recipient_count = fields.Integer(
        compute='_compute_recipient_stats', string="Destinatarios")
    sent_count = fields.Integer(compute='_compute_recipient_stats')
    failed_count = fields.Integer(compute='_compute_recipient_stats')
    pending_count = fields.Integer(compute='_compute_recipient_stats')
    queued_date = fields.Datetime(readonly=True, copy=False)
    sent_date = fields.Datetime(readonly=True, copy=False)

    @api.constrains('batch_size')
    def _check_batch_size(self):
        for campaign in self:
            if campaign.batch_size < 1:
                raise ValidationError(_('El tamaño de lote debe ser mayor que cero.'))

    @api.depends('target_rfm_a', 'target_rfm_b', 'target_rfm_c', 'target_category_ids',
                 'recipient_ids.state', 'state')
    def _compute_recipient_stats(self):
        for rec in self:
            if rec.state == 'draft':
                rec.recipient_count = len(rec._get_target_partners())
            else:
                rec.recipient_count = len(rec.recipient_ids)
            rec.sent_count = len(rec.recipient_ids.filtered(lambda r: r.state == 'sent'))
            rec.failed_count = len(rec.recipient_ids.filtered(lambda r: r.state == 'failed'))
            rec.pending_count = len(rec.recipient_ids.filtered(lambda r: r.state == 'pending'))

    def _target_categories(self):
        self.ensure_one()
        if self.target_category_ids:
            return self.target_category_ids.mapped('code')
        categories = []
        if self.target_rfm_a:
            categories.append('a')
        if self.target_rfm_b:
            categories.append('b')
        if self.target_rfm_c:
            categories.append('c')
        return categories

    def _get_target_partners(self):
        """Contactos de las categorías elegidas, con teléfono cargado y
        sin baja de WhatsApp: mismos criterios que ya usa
        action_create_rfm_marketing_list en res.partner, para no mandar
        mensajes a nadie que no se pueda o no corresponda contactar."""
        self.ensure_one()
        if self.segment_id:
            partners = self.segment_id.get_matching_partners()
            return partners.filtered(lambda partner: partner.phone and not partner.whatsapp_opt_out)
        categories = self._target_categories()
        if not categories:
            return self.env['res.partner']
        return self.env['res.partner'].search([
            ('rfm_category', 'in', categories),
            ('phone', '!=', False),
            ('whatsapp_opt_out', '=', False),
        ])

    def action_send(self):
        """Toma la foto de destinatarios y encola la campaña: el envío
        real lo hace _cron_process_campaigns en lotes, no este método.

        El chequeo de estado se hace con SELECT ... FOR UPDATE: dos clics
        (o dos requests) casi simultáneos en el mismo registro ya no pueden
        pasar los dos el "if state != draft" antes de que ninguno escriba,
        porque el segundo se bloquea en el lock hasta que el primero
        confirma su commit y cambia el estado."""
        self.ensure_one()
        self.env.cr.execute(
            "SELECT id FROM chatroom_campaign WHERE id = %s AND state = 'draft' FOR UPDATE",
            (self.id,))
        if not self.env.cr.fetchone():
            raise UserError(_("Esta campaña ya se encoló o se mandó."))
        partners = self._get_target_partners()
        if not partners:
            raise UserError(_(
                "No hay contactos que cumplan la segmentación elegida "
                "(con teléfono cargado y sin baja de WhatsApp)."))

        self.env['chatroom.campaign.recipient'].create([
            {'campaign_id': self.id, 'partner_id': partner.id} for partner in partners
        ])
        self.write({'state': 'sending', 'queued_date': fields.Datetime.now()})
        self.message_post(body=_(
            "Campaña encolada: %(total)s contactos objetivo, se van a mandar "
            "en lotes de %(batch)s cada 5 minutos."
        ) % {'total': len(partners), 'batch': self.batch_size})

    @api.model
    def _cron_process_campaigns(self):
        campaigns = self.search([('state', '=', 'sending')])
        Channel = self.env['chatroom.channel']
        for campaign in campaigns:
            batch_size = campaign.batch_size or 20
            pending = campaign.recipient_ids.filtered(lambda r: r.state == 'pending')[:batch_size]
            if not pending:
                campaign.write({'state': 'sent', 'sent_date': fields.Datetime.now()})
                campaign.message_post(body=_(
                    "Campaña terminada: %(sent)s mensajes mandados, %(failed)s "
                    "fallaron, sobre %(total)s contactos objetivo."
                ) % {
                    'sent': campaign.sent_count,
                    'failed': campaign.failed_count,
                    'total': len(campaign.recipient_ids),
                })
                continue

            for recipient in pending:
                partner = recipient.partner_id
                try:
                    channel_id = Channel.action_start_conversation(partner.id, phone=partner.phone)
                    channel = Channel.browse(channel_id)
                    values = campaign.template_id.get_variable_values(channel)
                    channel.action_send_template(
                        campaign.template_id.name, campaign.template_id.language, values)
                    recipient.state = 'sent'
                except Exception as exc:  # noqa: BLE001 - una falla individual no debe frenar el lote
                    _logger.exception(
                        "No se pudo enviar la campaña %s al contacto %s (%s)",
                        campaign.name, partner.name, partner.id)
                    recipient.write({'state': 'failed', 'error_message': str(exc)[:200]})

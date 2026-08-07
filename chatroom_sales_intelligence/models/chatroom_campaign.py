# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ChatroomCampaign(models.Model):
    """Envío masivo de una plantilla de WhatsApp (HSM) a los contactos de
    una o más categorías RFM (ej. reactivar la categoría C, agradecer a
    la A). Vive en este módulo -no en chatroom_whatsapp ni en
    crm_customer_intelligence- porque necesita los dos a la vez: la
    segmentación RFM y el canal de envío por WhatsApp."""
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
    state = fields.Selection(
        [('draft', "Borrador"), ('sent', "Enviada")],
        default='draft', required=True, copy=False)
    recipient_count = fields.Integer(
        compute='_compute_recipient_count', string="Destinatarios estimados")
    sent_count = fields.Integer(readonly=True, copy=False)
    failed_count = fields.Integer(readonly=True, copy=False)
    sent_date = fields.Datetime(readonly=True, copy=False)

    @api.depends('target_rfm_a', 'target_rfm_b', 'target_rfm_c')
    def _compute_recipient_count(self):
        for rec in self:
            rec.recipient_count = len(rec._get_target_partners())

    def _target_categories(self):
        self.ensure_one()
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
        categories = self._target_categories()
        if not categories:
            return self.env['res.partner']
        return self.env['res.partner'].search([
            ('rfm_category', 'in', categories),
            ('phone', '!=', False),
            ('whatsapp_opt_out', '=', False),
        ])

    def action_send(self):
        self.ensure_one()
        if self.state == 'sent':
            raise UserError(_("Esta campaña ya se mandó."))
        partners = self._get_target_partners()
        if not partners:
            raise UserError(_(
                "No hay contactos que cumplan la segmentación elegida "
                "(con teléfono cargado y sin baja de WhatsApp)."))

        Channel = self.env['chatroom.channel']
        sent = failed = 0
        for partner in partners:
            try:
                channel_id = Channel.action_start_conversation(partner.id, phone=partner.phone)
                channel = Channel.browse(channel_id)
                values = [partner.name] if self.template_id.variable_count else []
                channel.action_send_template(
                    self.template_id.name, self.template_id.language, values)
                sent += 1
            except Exception:  # noqa: BLE001 - una falla individual no debe frenar la campaña
                _logger.exception(
                    "No se pudo enviar la campaña %s al contacto %s (%s)",
                    self.name, partner.name, partner.id)
                failed += 1

        self.write({
            'state': 'sent',
            'sent_count': sent,
            'failed_count': failed,
            'sent_date': fields.Datetime.now(),
        })
        self.message_post(body=_(
            "Campaña enviada: %(sent)s mensajes mandados, %(failed)s fallaron, "
            "sobre %(total)s contactos objetivo."
        ) % {'sent': sent, 'failed': failed, 'total': len(partners)})

# -*- coding: utf-8 -*-
from odoo import fields, models


class ChatroomCampaignRecipient(models.Model):
    """Foto fija de a quién le toca una campaña, tomada en el momento en
    que se encola (action_send): así el cron que la procesa en lotes
    siempre trabaja sobre la misma lista, sin que un recálculo de RFM a
    mitad de camino (el cron diario de crm_customer_intelligence) sume o
    saque gente de una campaña que ya está en curso."""
    _name = 'chatroom.campaign.recipient'
    _description = "Destinatario de una campaña de WhatsApp"
    _order = 'id'

    campaign_id = fields.Many2one(
        'chatroom.campaign', required=True, ondelete='cascade', index=True)
    partner_id = fields.Many2one('res.partner', required=True, ondelete='cascade')
    state = fields.Selection(
        [('pending', "Pendiente"), ('sent', "Enviado"), ('failed', "Falló")],
        default='pending', required=True)
    error_message = fields.Char()

    _campaign_partner_unique = models.Constraint(
        'unique(campaign_id, partner_id)',
        'Este contacto ya está en la lista de destinatarios de la campaña.',
    )

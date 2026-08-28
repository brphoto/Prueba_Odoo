# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError, UserError


class CrmNpsCampaignWhatsapp(models.Model):
    _inherit = 'crm.nps.campaign'

    channel = fields.Selection(
        selection_add=[
            ('whatsapp', 'WhatsApp'),
            ('both', 'Correo y WhatsApp'),
        ],
        ondelete={'whatsapp': 'set default', 'both': 'set default'},
    )
    whatsapp_template_id = fields.Many2one(
        'chatroom.template', string='Plantilla de WhatsApp',
        domain=[('status', '=', 'approved')],
        help='Debe ser una plantilla aprobada por Meta. La primera variable {{1}} recibe el enlace individual de la encuesta.',
    )

    @api.constrains('channel', 'whatsapp_template_id')
    def _check_whatsapp_campaign(self):
        for campaign in self:
            if campaign.channel in ('whatsapp', 'both') and not campaign.whatsapp_template_id:
                raise ValidationError(_('Selecciona una plantilla de WhatsApp aprobada para este canal.'))
            template = campaign.whatsapp_template_id
            if template and template.variable_count < 1:
                raise ValidationError(_('La plantilla de WhatsApp debe tener al menos la variable {{1}} para insertar el enlace NPS.'))

    def _requested_channels(self):
        self.ensure_one()
        return ['email', 'whatsapp'] if self.channel == 'both' else [self.channel]

    def _send_whatsapp_recipient(self, line):
        self.ensure_one()
        partner = line.partner_id
        if partner.whatsapp_opt_out:
            line.write({'whatsapp_state': 'skipped', 'error_message': _('El contacto solicitó no recibir mensajes de WhatsApp.')})
            return
        if not partner.phone:
            line.write({'whatsapp_state': 'skipped', 'error_message': _('El contacto no tiene teléfono para WhatsApp.')})
            return
        template = self.whatsapp_template_id
        if not template or template.status != 'approved':
            raise UserError(_('La plantilla de WhatsApp debe estar aprobada por Meta.'))
        Channel = self.env['chatroom.channel']
        channel_id = Channel.action_start_conversation(partner.id, phone=partner.phone)
        channel = Channel.browse(channel_id)
        variables = [line.survey_url] + [''] * max(template.variable_count - 1, 0)
        channel.action_send_template(template.name, template.language, variables)
        line.write({'whatsapp_state': 'sent', 'sent_date': fields.Datetime.now(), 'error_message': False})

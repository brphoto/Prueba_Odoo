# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError


class CrmRfmSegmentActionWhatsapp(models.Model):
    _inherit = 'crm.rfm.segment.action'

    template_id = fields.Many2one(
        'chatroom.template', string='Plantilla WhatsApp',
        domain=[('status', '=', 'approved')])

    def _apply_to_partner(self, partner):
        if self.action_type != 'whatsapp_template':
            return super()._apply_to_partner(partner)
        if not self.template_id:
            raise UserError(_('Selecciona una plantilla aprobada para la acción WhatsApp.'))
        channel_model = self.env['chatroom.channel']
        channel_id = channel_model.action_start_conversation(partner.id, phone=partner.phone)
        channel = channel_model.browse(channel_id)
        values = self.template_id.get_variable_values(channel)
        channel.action_send_template(
            self.template_id.name, self.template_id.language, values)
        return True

# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    rfm_score = fields.Integer(related='partner_id.rfm_score', readonly=True)
    rfm_category = fields.Selection(related='partner_id.rfm_category', readonly=True)
    commercial_total_sales = fields.Monetary(
        related='partner_id.commercial_total_sales', readonly=True,
        # crm.lead usa 'company_currency' como currency_field propio
        # (no tiene 'currency_id'): sin esto, el campo Monetary no
        # encuentra dónde resolver la moneda y falla al cargar.
        currency_field='company_currency')
    commercial_last_sale_date = fields.Date(
        related='partner_id.commercial_last_sale_date', readonly=True)

    chatroom_channel_count = fields.Integer(compute='_compute_chatroom_channel_data')
    chatroom_last_message_preview = fields.Char(compute='_compute_chatroom_channel_data')
    chatroom_last_message_date = fields.Datetime(compute='_compute_chatroom_channel_data')

    def _get_chatroom_channels(self):
        """Todas las conversaciones de WhatsApp/Messenger/Instagram del
        contacto de esta oportunidad, más recientes primero. Se busca
        por partner_id (no hay un vínculo directo oportunidad->canal:
        el vínculo inverso ya existe, chatroom.channel.pinned_lead_id,
        pero es opcional y una conversación puede no tener ninguna
        oportunidad anclada todavía)."""
        self.ensure_one()
        if not self.partner_id:
            return self.env['chatroom.channel']
        return self.env['chatroom.channel'].search(
            [('partner_id', '=', self.partner_id.id)], order='last_message_date desc')

    def _compute_chatroom_channel_data(self):
        for lead in self:
            channels = lead._get_chatroom_channels()
            lead.chatroom_channel_count = len(channels)
            latest = channels[:1]
            lead.chatroom_last_message_preview = latest.last_message_preview if latest else False
            lead.chatroom_last_message_date = latest.last_message_date if latest else False

    def action_view_chatroom_channels(self):
        """Botón inteligente 'WhatsApp': con una sola conversación, la
        abre directo en su formulario como diálogo -funciona bien porque
        es una sola vista (a diferencia de un diálogo multi-vista tipo
        lista+form, que el framework no deja navegar adentro: ver la
        nota sobre switchView() en el README de chatroom_whatsapp). Con
        varias, abre la lista clásica navegando (sin forzar diálogo),
        que es el comportamiento estándar de cualquier smart button de
        Odoo y no tiene ese problema."""
        self.ensure_one()
        if not self.partner_id:
            raise UserError(_("Esta oportunidad no tiene un contacto asociado."))
        channels = self._get_chatroom_channels()
        if not channels:
            raise UserError(_(
                "%s todavía no tiene ninguna conversación de WhatsApp.") % self.partner_id.name)
        if len(channels) == 1:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'chatroom.channel',
                'res_id': channels.id,
                'views': [(False, 'form')],
                'target': 'new',
            }
        return {
            'type': 'ir.actions.act_window',
            'name': _("Conversaciones de WhatsApp"),
            'res_model': 'chatroom.channel',
            'views': [(False, 'list'), (False, 'kanban'), (False, 'form')],
            'domain': [('partner_id', '=', self.partner_id.id)],
        }

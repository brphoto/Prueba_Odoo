from odoo import _, api, fields, models


class MarketingSocialConversation(models.Model):
    _inherit = 'marketing.social.conversation'

    crm_lead_ids = fields.One2many(
        'crm.lead', 'marketing_conversation_id', string='Leads CRM')
    crm_lead_count = fields.Integer(
        compute='_compute_crm_lead_count', string='Leads CRM')

    @api.depends('crm_lead_ids')
    def _compute_crm_lead_count(self):
        for conversation in self:
            conversation.crm_lead_count = len(conversation.crm_lead_ids)

    def action_create_crm_lead(self):
        self.ensure_one()
        lead = self.crm_lead_ids[:1]
        if not lead:
            lead = self.env['crm.lead'].create({
                'name': _('Consulta social: %s') % (self.contact_name or self.name),
                'type': 'lead',
                'description': self.last_message_preview or '',
                'marketing_account_id': self.account_id.id,
                'marketing_conversation_id': self.id,
                'marketing_next_action': 'contact',
            })
            self.message_post(body=_('Se creó el lead CRM %s desde esta conversación.') % lead.display_name)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Lead comercial 360'),
            'res_model': 'crm.lead',
            'res_id': lead.id,
            'view_mode': 'form',
            'target': 'current',
        }

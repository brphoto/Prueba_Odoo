# -*- coding: utf-8 -*-
from odoo import _, fields, models


class CrmNpsInvitation(models.Model):
    _name = 'crm.nps.invitation'
    _description = 'Invitación NPS postventa'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc, id desc'

    partner_id = fields.Many2one('res.partner', string='Cliente', required=True, index=True)
    account_move_id = fields.Many2one('account.move', string='Factura pagada', required=True, ondelete='cascade', index=True)
    sale_order_id = fields.Many2one('sale.order', string='Pedido relacionado', ondelete='set null')
    survey_id = fields.Many2one('survey.survey', string='Encuesta', required=True,
                                default=lambda self: self.env.ref('crm_customer_experience.survey_nps', raise_if_not_found=False))
    state = fields.Selection([('pending', 'Pendiente'), ('sent', 'Enviada'), ('answered', 'Respondida')],
                             string='Estado', default='pending', tracking=True, index=True)
    sent_date = fields.Datetime(string='Enviada el', readonly=True)
    response_id = fields.Many2one('crm.nps.response', string='Respuesta', readonly=True)
    company_id = fields.Many2one('res.company', related='account_move_id.company_id', store=True)

    _invoice_unique = models.Constraint('UNIQUE (account_move_id)', 'Ya existe una invitación NPS para esta factura.')

    def action_open_survey(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'name': _('Encuesta NPS'), 'res_model': 'survey.survey',
                'res_id': self.survey_id.id, 'view_mode': 'form', 'target': 'current'}

    @classmethod
    def _is_enabled(cls, env):
        return env['ir.config_parameter'].sudo().get_param(
            'crm_customer_experience.auto_nps_invitation', '1') in ('1', 'True', 'true')

    def _cron_create_paid_invitations(self):
        if not self._is_enabled(self.env):
            return 0
        survey = self.env.ref('crm_customer_experience.survey_nps', raise_if_not_found=False)
        if not survey:
            return 0
        invoices = self.env['account.move'].sudo().search([
            ('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('payment_state', '=', 'paid'),
            ('partner_id', '!=', False),
        ])
        existing = self.search([('account_move_id', 'in', invoices.ids)]).mapped('account_move_id').ids
        pending = invoices.filtered(lambda invoice: invoice.id not in existing)
        self.create([{
            'partner_id': invoice.partner_id.id, 'account_move_id': invoice.id,
            'sale_order_id': invoice.invoice_line_ids.sale_line_ids.order_id[:1].id or False,
            'survey_id': survey.id,
        } for invoice in pending])
        return len(pending)

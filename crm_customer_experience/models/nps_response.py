# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class CrmNpsResponse(models.Model):
    _name = 'crm.nps.response'
    _description = 'Respuesta NPS'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'response_date desc, id desc'

    partner_id = fields.Many2one('res.partner', string='Cliente', required=True, index=True, tracking=True)
    score = fields.Integer(string='Puntuación (0–10)', required=True, tracking=True)
    category = fields.Selection([
        ('detractor', 'Detractor'), ('passive', 'Pasivo'), ('promoter', 'Promotor'),
    ], string='Clasificación', compute='_compute_category', store=True, index=True)
    reason = fields.Text(string='Motivo o comentario')
    response_date = fields.Date(string='Fecha de respuesta', required=True, default=fields.Date.context_today, index=True)
    survey_user_input_id = fields.Many2one('survey.user_input', string='Respuesta de Encuesta',
                                           ondelete='set null', index=True, copy=False)
    sale_order_id = fields.Many2one('sale.order', string='Pedido relacionado', ondelete='set null')
    account_move_id = fields.Many2one('account.move', string='Factura relacionada', ondelete='set null')
    company_id = fields.Many2one('res.company', string='Empresa', required=True, default=lambda self: self.env.company)
    source = fields.Selection([('manual', 'Registro manual'), ('survey', 'Encuesta NPS'), ('import', 'Importación')],
                              string='Origen', default='manual', required=True)

    _survey_unique = models.Constraint('UNIQUE (survey_user_input_id)',
                                       'Cada respuesta de Encuesta NPS solo puede generar un registro NPS.')

    @api.depends('score')
    def _compute_category(self):
        for record in self:
            record.category = 'detractor' if record.score <= 6 else ('passive' if record.score <= 8 else 'promoter')

    @api.constrains('score')
    def _check_score(self):
        for record in self:
            if not 0 <= record.score <= 10:
                raise ValidationError(_('La puntuación NPS debe estar entre 0 y 10.'))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        partners = records.mapped('partner_id')
        partners._refresh_nps_summary(partners.ids)
        return records

    def write(self, vals):
        result = super().write(vals)
        partners = self.mapped('partner_id')
        partners._refresh_nps_summary(partners.ids)
        return result

    def unlink(self):
        partner_ids = self.mapped('partner_id').ids
        result = super().unlink()
        self.env['res.partner']._refresh_nps_summary(partner_ids)
        return result

    def action_schedule_followup(self):
        self.ensure_one()
        return self.partner_id.action_schedule_nps_followup()

    @api.model
    def global_nps(self):
        total = self.search_count([])
        promoters = self.search_count([('category', '=', 'promoter')])
        detractors = self.search_count([('category', '=', 'detractor')])
        return ((promoters - detractors) / total * 100.0) if total else 0.0

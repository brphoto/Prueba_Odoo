from odoo import _, api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    history_line_ids = fields.One2many(
        'crm.customer.history.line', 'partner_id', string='Históricos comerciales')
    history_invoice_count = fields.Integer(
        string='Facturas históricas', compute='_compute_history_metrics')
    history_total_amount = fields.Monetary(
        string='Total histórico', currency_field='currency_id', compute='_compute_history_metrics')
    history_last_purchase_date = fields.Date(
        string='Última compra histórica', compute='_compute_history_metrics')
    history_average_ticket = fields.Monetary(
        string='Ticket histórico promedio', currency_field='currency_id', compute='_compute_history_metrics')
    history_manual_category_id = fields.Many2one(
        'crm.rfm.segment', string='Categoría manual',
        domain=[('definition_type', '=', 'category'), ('active', '=', True)], copy=False)
    history_manual_category_reason = fields.Text(string='Motivo de categoría manual', copy=False)
    history_manual_category_date = fields.Date(string='Fecha de categoría manual', readonly=True, copy=False)
    history_category_source = fields.Selection([
        ('automatic', 'Automática'), ('manual', 'Manual'),
    ], string='Origen de categoría', compute='_compute_history_category_source')

    history_manual_category_changed_by = fields.Many2one(
        'res.users', string='Categoría cambiada por', readonly=True, copy=False)
    history_manual_category_previous = fields.Char(
        string='Categoría anterior', readonly=True, copy=False)

    @api.depends('history_line_ids.state', 'history_line_ids.batch_id.state', 'history_line_ids.company_amount_total', 'history_line_ids.invoice_date')
    def _compute_history_metrics(self):
        for partner in self:
            lines = partner.history_line_ids.filtered(
                lambda line: line.state == 'valid' and line.batch_id.state == 'approved')
            total = sum(lines.mapped('company_amount_total'))
            partner.history_invoice_count = len(lines)
            partner.history_total_amount = total
            partner.history_last_purchase_date = max(lines.mapped('invoice_date')) if lines else False
            partner.history_average_ticket = total / len(lines) if lines else 0.0

    @api.depends('history_manual_category_id', 'rfm_category')
    def _compute_history_category_source(self):
        for partner in self:
            partner.history_category_source = 'manual' if partner.history_manual_category_id else 'automatic'

    def write(self, vals):
        if 'history_manual_category_id' in vals:
            vals = dict(vals)
            previous_category = self[:1].rfm_category if len(self) == 1 else False
            vals['history_manual_category_date'] = fields.Date.context_today(self) if vals['history_manual_category_id'] else False
            vals['history_manual_category_changed_by'] = self.env.user.id if vals['history_manual_category_id'] else False
            vals['history_manual_category_previous'] = previous_category if vals['history_manual_category_id'] else False
        result = super().write(vals)
        if 'history_manual_category_id' in vals:
            for partner in self:
                if partner.history_manual_category_id:
                    partner.rfm_category = partner.history_manual_category_id.code
        return result

    @api.model
    def _get_rfm_external_rows(self):
        rows = super()._get_rfm_external_rows()
        Line = self.env['crm.customer.history.line']
        grouped = Line._read_group([
            ('state', '=', 'valid'), ('batch_id.state', '=', 'approved'), ('partner_id', '!=', False),
        ], groupby=['partner_id'], aggregates=['company_amount_total:sum', '__count', 'invoice_date:max'])
        for partner, total, count, last_date in grouped:
            if not partner:
                continue
            current = rows.setdefault(partner.id, {
                'partner': partner, 'total': 0.0, 'count': 0, 'last_date': False,
            })
            current['total'] += total or 0.0
            current['count'] += count or 0
            if last_date and (not current['last_date'] or last_date > current['last_date']):
                current['last_date'] = last_date
        return rows

    @api.model
    def _get_rfm_dashboard_external_rows(self, partner_ids, date_from=False, date_to=False):
        rows = super()._get_rfm_dashboard_external_rows(partner_ids, date_from, date_to)
        domain = [
            ('state', '=', 'valid'), ('batch_id.state', '=', 'approved'),
            ('partner_id', 'in', partner_ids or [0]),
        ]
        if date_from:
            domain.append(('invoice_date', '>=', date_from))
        if date_to:
            domain.append(('invoice_date', '<', date_to))
        grouped = self.env['crm.customer.history.line']._read_group(
            domain, groupby=['partner_id'],
            aggregates=['company_amount_total:sum', '__count'])
        rows.extend({
            'partner': partner,
            'total': total or 0.0,
            'invoice_count': count or 0,
        } for partner, total, count in grouped if partner)
        return rows

    @api.model
    def _get_rfm_dashboard_evolution_external_rows(self, partner_ids, date_from, date_to=False):
        domain = [
            ('state', '=', 'valid'), ('batch_id.state', '=', 'approved'),
            ('partner_id', 'in', partner_ids or [0]),
            ('invoice_date', '>=', date_from),
        ]
        if date_to:
            domain.append(('invoice_date', '<', date_to))
        lines = self.env['crm.customer.history.line'].search(domain)
        return [{
            'date': line.invoice_date,
            'total': line.company_amount_total,
            'invoice_count': 1,
        } for line in lines]

    def _cron_compute_rfm_scores(self, date_from=None, date_to=None):
        result = super()._cron_compute_rfm_scores(date_from=date_from, date_to=date_to)
        manual = self.search([('history_manual_category_id', '!=', False)])
        for partner in manual:
            partner.rfm_category = partner.history_manual_category_id.code
        return result

    def action_open_history_lines(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Históricos de %s') % self.display_name,
            'res_model': 'crm.customer.history.line',
            'view_mode': 'list,form',
            'domain': [('partner_id', '=', self.id)],
            'context': {'search_default_valid_approved': 1},
            'target': 'current',
        }

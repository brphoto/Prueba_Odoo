from odoo import models, fields, api

class CrmLead(models.Model):
    _inherit = 'crm.lead'

    poliza_count = fields.Integer(string="Cantidad de Pólizas", compute="_compute_poliza_count")

    def _compute_poliza_count(self):
        for rec in self:
            rec.poliza_count = self.env['poliza.partner'].search_count([('partner_id', '=', rec.id)])

    def action_ver_polizas(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Pólizas del Cliente',
            'res_model': 'poliza.partner',
            'view_mode': 'list,form',
            'target': 'current',
            'domain': [('partner_id', '=', self.id)],
            'context': {'default_partner_id': self.id},
        }

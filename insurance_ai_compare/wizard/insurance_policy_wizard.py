# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.insurance_compare import to_number


class InsurancePolicyWizard(models.TransientModel):
    """Convierte la opción elegida por el cliente en una póliza."""
    _name = 'insurance.policy.wizard'
    _description = 'Emitir póliza desde el comparativo'

    compare_id = fields.Many2one('insurance.compare', required=True, readonly=True)
    offer_id = fields.Many2one(
        'insurance.compare.offer', string='Opción elegida por el cliente', required=True,
        domain="[('compare_id', '=', compare_id), ('disqualified', '=', False)]")
    numero_poliza = fields.Char(string='Número de póliza', required=True)
    fecha_inicio = fields.Date(string='Inicio de vigencia', required=True, default=fields.Date.context_today)
    executive_id = fields.Many2one('polizas.ramos', string='Ejecutivo', required=True)
    poliza_type_id = fields.Many2one('poliza.type', string='Tipo de póliza', required=True)
    ramo_id = fields.Many2one('poliza.ramo', string='Ramo')
    tipo_pago = fields.Selection([('contado', 'Contado'), ('cuotas', 'Cuotas')],
                                 string='Tipo de pago', required=True, default='contado')
    coverage_count = fields.Integer(compute='_compute_coverage_count', string='Coberturas a copiar')

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        compare = self.env['insurance.compare'].browse(values.get('compare_id'))
        if compare and 'ramo_id' in fields_list and not values.get('ramo_id'):
            values['ramo_id'] = compare.template_id.ramo_id.id
        return values

    @api.depends('offer_id')
    def _compute_coverage_count(self):
        for wizard in self:
            wizard.coverage_count = len(wizard._coverage_lines())

    def _coverage_lines(self):
        return self.offer_id.line_ids.filtered(lambda line: line.state in ('yes', 'limited'))

    def action_confirm(self):
        self.ensure_one()
        compare, offer = self.compare_id, self.offer_id
        if offer.compare_id != compare:
            raise UserError(_('La opción no pertenece a este comparativo.'))
        if offer.disqualified:
            raise UserError(_('La opción elegida está descartada: %s') % offer.disqualified_reason)
        coverages = []
        for line in self._coverage_lines():
            amount = to_number(line.limit_text)
            coverages.append((0, 0, {
                'name': (line.coverage_id.name or line.name)[:250],
                'insured_amount': amount if amount and amount > 0 else (offer.sum_insured or 0.0),
                'deductible': max(to_number(line.deductible_text) or 0.0, 0.0),
                'description': '\n'.join(filter(None, [
                    line.name if line.coverage_id and line.name != line.coverage_id.name else '',
                    _('Límite: %s') % line.limit_text if line.limit_text else '',
                    _('Estado: limitada') if line.state == 'limited' else '',
                ])) or False,
            }))
        policy = self.env['poliza.partner'].create({
            'partner_id': compare.partner_id.id,
            'ramo_id': self.executive_id.id,
            'aseguradora_id': offer.insurer_id.id,
            'numero_poliza': self.numero_poliza,
            'fecha_inicio': self.fecha_inicio,
            'poliza_type': self.poliza_type_id.id,
            'tipo_pago': self.tipo_pago,
            'ramos_id': self.ramo_id.id or False,
            'prima_neta': offer.premium_net,
            'prima_total': offer.premium_total,
            'cobertura_ids': coverages,
        })
        compare.write({'state': 'won', 'chosen_offer_id': offer.id, 'policy_id': policy.id})
        compare.message_post(body=_('Póliza %(policy)s emitida con %(insurer)s.') % {
            'policy': policy.display_name, 'insurer': offer.insurer_id.name})
        return {
            'type': 'ir.actions.act_window', 'res_model': 'poliza.partner', 'res_id': policy.id,
            'view_mode': 'form', 'views': [(False, 'form')], 'target': 'current',
        }

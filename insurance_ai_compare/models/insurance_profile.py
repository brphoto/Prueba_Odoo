# -*- coding: utf-8 -*-
import json

from odoo import _, api, fields, models


class InsuranceClientProfile(models.Model):
    """Datos del cliente para cotizar un ramo, reunidos desde la conversación
    o a mano. Cada dato guarda de qué mensaje salió."""
    _name = 'insurance.client.profile'
    _description = 'Perfil de riesgo del cliente'
    _inherit = ['mail.thread']
    _order = 'write_date desc, id desc'
    _rec_name = 'display_name'

    partner_id = fields.Many2one('res.partner', string='Cliente', required=True, index=True, tracking=True)
    template_id = fields.Many2one(
        'insurance.compare.template', string='Ramo / plantilla', required=True, tracking=True)
    company_id = fields.Many2one(
        'res.company', string='Empresa', default=lambda self: self.env.company, required=True)
    channel_id = fields.Many2one('chatroom.channel', string='Conversación de origen')
    data_json = fields.Text(string='Datos (JSON)', default='{}')
    summary = fields.Text(string='Resumen del perfil', tracking=True)
    priorities = fields.Text(
        string='Qué valora el cliente', tracking=True,
        help='Por ejemplo: precio bajo, auto de reemplazo, deducible mínimo.')
    missing_fields = fields.Text(string='Datos que faltan', compute='_compute_missing', store=True)
    completion = fields.Float(string='Completo (%)', compute='_compute_missing', store=True)

    _partner_template_uniq = models.Constraint(
        'unique(partner_id, template_id, company_id)',
        'El cliente ya tiene un perfil para ese ramo.',
    )

    @api.depends('partner_id', 'template_id')
    def _compute_display_name(self):
        for profile in self:
            profile.display_name = '%s · %s' % (
                profile.partner_id.name or '', profile.template_id.name or '')

    def _data(self):
        self.ensure_one()
        try:
            data = json.loads(self.data_json or '{}')
        except ValueError:
            data = {}
        return data if isinstance(data, dict) else {}

    @api.depends('data_json', 'template_id.profile_fields')
    def _compute_missing(self):
        for profile in self:
            fields_list = profile.template_id._profile_field_list() if profile.template_id else []
            data = profile._data()
            missing = [label for key, label in fields_list
                       if data.get(key) in (None, '', [], {})]
            profile.missing_fields = '\n'.join(missing)
            profile.completion = (100.0 * (len(fields_list) - len(missing)) / len(fields_list)
                                  if fields_list else 100.0)

    def _merge_data(self, values):
        """Agrega datos nuevos sin borrar los que ya había."""
        self.ensure_one()
        data = self._data()
        for key, value in (values or {}).items():
            if value not in (None, '', [], {}):
                data[key] = value
        self.data_json = json.dumps(data, ensure_ascii=False, indent=2)

    def _as_prompt(self):
        """Perfil en texto para la IA (solo los campos del ramo, sin extras)."""
        self.ensure_one()
        data = self._data()
        lines = ['%s: %s' % (label, data[key]) for key, label in self.template_id._profile_field_list()
                 if data.get(key) not in (None, '', [], {})]
        if self.priorities:
            lines.append(_('Prioridades del cliente: %s') % self.priorities)
        return '\n'.join(lines) or _('Sin datos del cliente todavía.')

    def action_open_compare(self):
        self.ensure_one()
        compare = self.env['insurance.compare'].create({
            'partner_id': self.partner_id.id,
            'template_id': self.template_id.id,
            'profile_id': self.id,
            'channel_id': self.channel_id.id,
        })
        return compare._action_open_form()

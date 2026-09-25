# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    data_consent_count = fields.Integer(compute="_compute_data_consent_count")

    @api.depends()
    def _compute_data_consent_count(self):
        data = self.env["ec.data.consent"]._read_group(
            [("partner_id", "in", self.ids)], ["partner_id"], ["__count"]
        )
        consent_map = {partner.id: count for partner, count in data}
        for partner in self:
            partner.data_consent_count = consent_map.get(partner.id, 0)

    def action_view_data_consents(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Consentimientos de Datos",
            "res_model": "ec.data.consent",
            "view_mode": "list,form",
            "domain": [("partner_id", "=", self.id)],
            "context": {"default_partner_id": self.id},
        }

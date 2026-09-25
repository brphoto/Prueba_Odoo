# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class EcDataConsentType(models.Model):
    _name = "ec.data.consent.type"
    _description = "Tipo de Consentimiento de Datos Personales"

    name = fields.Char("Nombre", required=True)
    code = fields.Char("Código")
    description = fields.Text("Descripción / Finalidad del Tratamiento")
    active = fields.Boolean(default=True)


class EcDataConsent(models.Model):
    _name = "ec.data.consent"
    _description = "Consentimiento de Tratamiento de Datos Personales"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_given desc, id desc"

    def init(self):
        # Un socio no puede tener dos consentimientos "Otorgado" activos del mismo
        # tipo a la vez (evita que un doble-envío del portal deje un otorgamiento
        # "fantasma" vigente después de revocar el otro, ver has_active_consent()).
        self.env.cr.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS ec_data_consent_partner_type_granted_uniq
            ON ec_data_consent (partner_id, consent_type_id)
            WHERE state = 'granted'
        """)

    name = fields.Char("Referencia", compute="_compute_name", store=True)
    partner_id = fields.Many2one("res.partner", "Socio / Contacto", required=True, tracking=True)
    consent_type_id = fields.Many2one(
        "ec.data.consent.type", "Tipo de Consentimiento", required=True, tracking=True
    )
    date_given = fields.Date("Fecha de Otorgamiento", required=True, default=fields.Date.context_today)
    policy_version = fields.Char("Versión de Política Aceptada", required=True, default="1.0")
    signed_by = fields.Char(
        "Firmado/Aceptado Por",
        help="Nombre de quien otorgó el consentimiento (puede diferir del socio, ej. tutor legal).",
    )
    registered_by_id = fields.Many2one(
        "res.users", "Registrado Por", readonly=True, default=lambda self: self.env.user
    )
    state = fields.Selection(
        [("granted", "Otorgado"), ("revoked", "Revocado")],
        default="granted", required=True, copy=False, tracking=True,
    )
    date_revoked = fields.Date("Fecha de Revocación", readonly=True, copy=False)
    revoke_reason = fields.Char("Motivo de Revocación", copy=False)

    @api.depends("partner_id.name", "consent_type_id.name")
    def _compute_name(self):
        for rec in self:
            rec.name = "%s - %s" % (rec.partner_id.name or "", rec.consent_type_id.name or "")

    def action_revoke(self):
        for rec in self:
            if rec.state == "revoked":
                raise UserError(_("Este consentimiento ya está revocado."))
            rec.write({
                "state": "revoked",
                "date_revoked": fields.Date.context_today(rec),
            })

    @api.model
    def has_active_consent(self, partner_id, consent_type_code):
        """Utilidad para que otros módulos verifiquen si un socio tiene un
        consentimiento vigente de un tipo determinado, sin tener que conocer
        el modelo de consentimiento por dentro."""
        return bool(self.search_count([
            ("partner_id", "=", partner_id),
            ("consent_type_id.code", "=", consent_type_code),
            ("state", "=", "granted"),
        ]))

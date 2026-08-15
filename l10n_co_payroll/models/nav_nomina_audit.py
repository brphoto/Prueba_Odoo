from odoo import _, fields, models


class NavNominaAudit(models.Model):
    _name = "nav.nomina.audit"
    _description = "Trazabilidad de nómina Colombia"
    _order = "event_at desc, id desc"
    _check_company_auto = True

    company_id = fields.Many2one("res.company", required=True, index=True, default=lambda self: self.env.company)
    period_id = fields.Many2one("nav.nomina.period", string="Periodo", ondelete="cascade", index=True)
    res_model = fields.Char(string="Modelo", required=True, readonly=True)
    res_id = fields.Integer(string="Registro", required=True, readonly=True)
    action = fields.Selection([
        ("prepare", "Preparar"), ("validate", "Validar"), ("approve", "Aprobar"),
        ("reject", "Rechazar"), ("close", "Cerrar"), ("cancel", "Cancelar"),
        ("export", "Exportar"), ("accounting", "Contabilizar"), ("payment", "Pago"),
        ("pila", "PILA"), ("settlement", "Liquidación"), ("other", "Otro"),
    ], string="Acción", required=True, readonly=True)
    description = fields.Text(string="Descripción", required=True, readonly=True)
    event_at = fields.Datetime(string="Fecha", required=True, readonly=True, default=fields.Datetime.now, index=True)
    user_id = fields.Many2one("res.users", string="Usuario", required=True, readonly=True, default=lambda self: self.env.user)

    def name_get(self):
        return [(record.id, _("%s - %s") % (record.action, record.event_at)) for record in self]

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CoPayrollSetupWizard(models.TransientModel):
    _name = "l10n.co.payroll.setup.wizard"
    _description = "Configuración inicial de nómina colombiana"

    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, readonly=True)
    parameter_id = fields.Many2one("l10n.co.payroll.parameter", string="Versión legal", readonly=True)
    year = fields.Integer(string="Año", required=True, default=lambda self: fields.Date.context_today(self).year)
    minimum_wage = fields.Monetary(string="Salario mínimo", currency_field="currency_id", required=True)
    transport_allowance = fields.Monetary(string="Auxilio de transporte", currency_field="currency_id")
    uvt_value = fields.Monetary(string="Valor UVT")
    weekly_hours = fields.Float(string="Jornada semanal", default=42.0)
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)
    pila_config_id = fields.Many2one("l10n.co.payroll.pila.config", string="Configuración PILA", readonly=True)

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        company = self.env.company
        year = values.get("year") or fields.Date.context_today(self).year
        parameter = self.env["l10n.co.payroll.parameter"].search(
            [("company_id", "=", company.id), ("year", "=", year)],
            order="status desc, version desc",
            limit=1,
        )
        pila = self.env["l10n.co.payroll.pila.config"].search(
            [("company_id", "=", company.id), ("active", "=", True)], order="id", limit=1
        )
        if parameter:
            values.update({
                "parameter_id": parameter.id,
                "minimum_wage": parameter.minimum_wage,
                "transport_allowance": parameter.transport_allowance,
                "uvt_value": parameter.uvt_value,
                "weekly_hours": parameter.weekly_hours,
            })
        values["pila_config_id"] = pila.id
        return values

    def action_apply(self):
        self.ensure_one()
        if self.year < 2000:
            raise UserError(_("Indica un año válido."))
        if self.minimum_wage <= 0:
            raise UserError(_("El salario mínimo debe ser mayor que cero."))
        Parameter = self.env["l10n.co.payroll.parameter"].sudo()
        parameter = self.parameter_id or Parameter.search(
            [("company_id", "=", self.company_id.id), ("year", "=", self.year)],
            order="version desc",
            limit=1,
        )
        values = {
            "company_id": self.company_id.id,
            "year": self.year,
            "effective_from": "%s-01-01" % self.year,
            "effective_to": "%s-12-31" % self.year,
            "minimum_wage": self.minimum_wage,
            "transport_allowance": self.transport_allowance,
            "uvt_value": self.uvt_value,
            "weekly_hours": self.weekly_hours or 42.0,
            "source_reference": parameter.source_reference if parameter else _("Parametrización inicial Colombia"),
        }
        if parameter:
            parameter.write(values)
        else:
            values.update({"version": 1, "status": "active"})
            parameter = Parameter.create(values)
        pila = self.env["l10n.co.payroll.pila.config"].sudo().search(
            [("company_id", "=", self.company_id.id)], order="id", limit=1
        )
        if not pila:
            pila = self.env["l10n.co.payroll.pila.config"].sudo().create({
                "name": "PILA Colombia - archivo configurable",
                "company_id": self.company_id.id,
                "operator": "generic",
                "file_format": "csv",
                "delimiter": ";",
                "encoding": "cp1252",
                "filename_prefix": "PILA_COLOMBIA",
                "legal_reference": _("Configuración inicial. Validar el formato del operador antes de transmitir."),
            })
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Parametrización guardada"),
                "message": _("La versión legal y la configuración PILA están listas para crear periodos."),
                "type": "success",
                "sticky": False,
            },
        }

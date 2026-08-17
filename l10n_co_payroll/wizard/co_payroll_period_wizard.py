from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models


class CoPayrollPeriodWizard(models.TransientModel):
    _name = "l10n.co.payroll.period.wizard"
    _description = "Crear periodo de nómina"

    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    period_type = fields.Selection([("monthly", "Mensual"), ("biweekly", "Quincenal"), ("weekly", "Semanal"), ("off_cycle", "Extraordinario")], string="Frecuencia", required=True, default="monthly")
    date_from = fields.Date(string="Desde", required=True, default=lambda self: fields.Date.context_today(self).replace(day=1))
    date_to = fields.Date(string="Hasta", required=True, default=lambda self: fields.Date.context_today(self) + relativedelta(day=31))
    payment_date = fields.Date(string="Fecha de pago")
    employee_ids = fields.Many2many("hr.employee", string="Empleados")
    department_ids = fields.Many2many("hr.department", string="Departamentos")
    job_ids = fields.Many2many("hr.job", string="Cargos")
    structure_ids = fields.Many2many("hr.payroll.structure", string="Estructuras salariales")
    note = fields.Text(string="Notas")

    @api.onchange("date_from", "period_type")
    def _onchange_dates(self):
        if not self.date_from:
            return
        if self.period_type == "monthly":
            self.date_to = self.date_from + relativedelta(day=31)
        elif self.period_type == "biweekly":
            self.date_to = self.date_from.replace(day=15)
        elif self.period_type == "weekly":
            self.date_to = self.date_from + relativedelta(days=6)

    def action_create_period(self):
        self.ensure_one()
        period = self.env["l10n.co.payroll.period"].create({
            "company_id": self.company_id.id,
            "period_type": self.period_type,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "payment_date": self.payment_date,
            "employee_ids": [(6, 0, self.employee_ids.ids)],
            "department_ids": [(6, 0, self.department_ids.ids)],
            "job_ids": [(6, 0, self.job_ids.ids)],
            "structure_ids": [(6, 0, self.structure_ids.ids)],
            "note": self.note,
        })
        return {"type": "ir.actions.act_window", "name": _("Periodo de nómina"), "res_model": "l10n.co.payroll.period", "view_mode": "form", "res_id": period.id, "target": "current"}

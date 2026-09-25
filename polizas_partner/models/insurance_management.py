from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class PolizaPartner(models.Model):
    _inherit = "poliza.partner"

    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Moneda",
        related="company_id.currency_id",
        store=True,
        readonly=True,
    )
    cobertura_ids = fields.One2many(
        "poliza.cobertura", "poliza_id", string="Coberturas", copy=True
    )
    bien_asegurado_ids = fields.One2many(
        "poliza.bien.asegurado", "poliza_id", string="Bienes asegurados", copy=True
    )
    siniestro_ids = fields.One2many(
        "poliza.siniestro", "poliza_id", string="Siniestros", copy=False
    )
    devengamiento_ids = fields.One2many(
        "poliza.devengamiento", "poliza_id", string="Devengamientos", copy=False
    )
    devengamiento_automatico = fields.Boolean(
        string="Devengamiento mensual automático", default=True
    )
    prima_mensual = fields.Monetary(
        string="Prima mensual", compute="_compute_prima_mensual", store=True
    )
    journal_devengamiento_id = fields.Many2one(
        "account.journal",
        string="Diario de devengamiento",
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]",
        check_company=True,
    )
    account_expense_id = fields.Many2one(
        "account.account",
        string="Cuenta de gasto",
        domain="[('company_ids', 'in', company_id)]",
        check_company=True,
    )
    account_prepaid_id = fields.Many2one(
        "account.account",
        string="Cuenta de seguros pagados por anticipado",
        domain="[('company_ids', 'in', company_id)]",
        check_company=True,
    )
    devengamiento_count = fields.Integer(
        string="Nº de devengamientos", compute="_compute_insurance_counts"
    )
    siniestro_count = fields.Integer(
        string="Nº de siniestros", compute="_compute_insurance_counts"
    )

    @api.depends("prima_total", "fecha_inicio", "fecha_fin")
    def _compute_prima_mensual(self):
        for policy in self:
            if not policy.prima_total or not policy.fecha_inicio or not policy.fecha_fin:
                policy.prima_mensual = 0.0
                continue
            months = (
                (policy.fecha_fin.year - policy.fecha_inicio.year) * 12
                + policy.fecha_fin.month
                - policy.fecha_inicio.month
                + 1
            )
            policy.prima_mensual = policy.prima_total / max(months, 1)

    @api.depends("devengamiento_ids", "siniestro_ids")
    def _compute_insurance_counts(self):
        for policy in self:
            policy.devengamiento_count = len(policy.devengamiento_ids)
            policy.siniestro_count = len(policy.siniestro_ids)

    @api.constrains("company_id", "fecha_inicio", "fecha_fin")
    def _check_insurance_dates(self):
        for policy in self:
            if policy.fecha_inicio and policy.fecha_fin and policy.fecha_fin < policy.fecha_inicio:
                raise ValidationError(_("La fecha final no puede ser anterior a la fecha inicial."))

    def action_generar_devengamientos(self):
        """Create one draft recognition line for every month of the policy."""
        for policy in self:
            if not policy.fecha_inicio or not policy.fecha_fin:
                raise UserError(_("La póliza debe tener fechas de inicio y fin."))
            if policy.prima_total <= 0:
                raise UserError(_("La póliza debe tener una prima total mayor que cero."))

            first_month = fields.Date.start_of(policy.fecha_inicio, "month")
            last_month = fields.Date.start_of(policy.fecha_fin, "month")
            total_months = (
                (last_month.year - first_month.year) * 12
                + last_month.month
                - first_month.month
                + 1
            )
            monthly_amount = policy.currency_id.round(policy.prima_total / total_months)
            existing_periods = set(policy.devengamiento_ids.mapped("period_date"))
            created_amount = sum(policy.devengamiento_ids.mapped("amount"))

            for index in range(total_months):
                period_date = first_month + relativedelta(months=index)
                if period_date in existing_periods:
                    continue
                amount = monthly_amount
                if index == total_months - 1:
                    amount = policy.prima_total - created_amount
                self.env["poliza.devengamiento"].create(
                    {
                        "poliza_id": policy.id,
                        "period_date": period_date,
                        "amount": amount,
                    }
                )
                created_amount += amount
        return True

    def action_post_devengamientos(self):
        for policy in self:
            policy.action_generar_devengamientos()
            policy.devengamiento_ids.filtered(lambda line: line.state == "draft").action_post()
        return True

    @api.model
    def cron_generar_devengamiento_mensual(self):
        today = fields.Date.today()
        policies = self.search(
            [
                ("devengamiento_automatico", "=", True),
                ("state", "=", "vigente"),
                ("fecha_inicio", "<=", today),
                ("fecha_fin", ">=", today),
            ]
        )
        current_period = fields.Date.start_of(today, "month")
        for policy in policies:
            policy.action_generar_devengamientos()
            line = policy.devengamiento_ids.filtered(
                lambda item: item.period_date == current_period and item.state == "draft"
            )[:1]
            if line and policy.journal_devengamiento_id and policy.account_expense_id and policy.account_prepaid_id:
                line.action_post()
        return True

    def _copy_insurance_details_to(self, target_policy):
        """Carry institutional insurance data to a renewal policy."""
        self.ensure_one()
        target_policy.write(
            {
                "company_id": self.company_id.id,
                "devengamiento_automatico": self.devengamiento_automatico,
                "journal_devengamiento_id": self.journal_devengamiento_id.id,
                "account_expense_id": self.account_expense_id.id,
                "account_prepaid_id": self.account_prepaid_id.id,
            }
        )
        for coverage in self.cobertura_ids:
            coverage.copy({"poliza_id": target_policy.id})
        for item in self.bien_asegurado_ids:
            item.copy({"poliza_id": target_policy.id})
        return target_policy


class PolizaCobertura(models.Model):
    _name = "poliza.cobertura"
    _description = "Cobertura de póliza"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    name = fields.Char(string="Cobertura", required=True)
    poliza_id = fields.Many2one(
        "poliza.partner", string="Póliza", required=True, ondelete="cascade", index=True
    )
    company_id = fields.Many2one(related="poliza_id.company_id", store=True)
    currency_id = fields.Many2one(related="poliza_id.currency_id", store=True)
    description = fields.Text(string="Descripción")
    insured_amount = fields.Monetary(string="Suma asegurada", required=True)
    deductible = fields.Monetary(string="Deducible")
    premium_amount = fields.Monetary(string="Prima de cobertura")
    active = fields.Boolean(default=True)

    @api.constrains("insured_amount", "deductible", "premium_amount")
    def _check_amounts(self):
        for coverage in self:
            if coverage.insured_amount < 0 or coverage.deductible < 0 or coverage.premium_amount < 0:
                raise ValidationError(_("Los importes de una cobertura no pueden ser negativos."))


class PolizaBienAsegurado(models.Model):
    _name = "poliza.bien.asegurado"
    _description = "Bien asegurado"
    _order = "name, id"

    name = fields.Char(string="Bien asegurado", required=True)
    poliza_id = fields.Many2one(
        "poliza.partner", string="Póliza", required=True, ondelete="cascade", index=True
    )
    company_id = fields.Many2one(related="poliza_id.company_id", store=True)
    currency_id = fields.Many2one(related="poliza_id.currency_id", store=True)
    asset_id = fields.Many2one(
        "poliza.activo",
        string="Bien / activo",
        ondelete="set null",
        check_company=True,
        domain="[('company_id', '=', company_id)]",
    )
    asset_state = fields.Selection(related="asset_id.state", string="Estado del activo")
    asset_value = fields.Monetary(
        string="Valor contable", related="asset_id.book_value", readonly=True
    )
    serial_number = fields.Char(string="Serie / placa")
    location = fields.Char(string="Ubicación")
    insured_amount = fields.Monetary(string="Valor asegurado", required=True)
    notes = fields.Text(string="Observaciones")
    active = fields.Boolean(default=True)

    @api.constrains("insured_amount")
    def _check_insured_amount(self):
        for item in self:
            if item.insured_amount < 0:
                raise ValidationError(_("El valor asegurado no puede ser negativo."))


class PolizaActivo(models.Model):
    """Registro ligero de activos asegurables para Odoo Community.

    Odoo Community no incluye el módulo Enterprise de activos fijos. Este
    modelo cubre la información que necesita la gestión de pólizas sin esa
    dependencia.
    """

    _name = "poliza.activo"
    _description = "Bien o activo asegurable"
    _order = "name, id"

    name = fields.Char(string="Nombre", required=True)
    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Moneda",
        related="company_id.currency_id",
        readonly=True,
    )
    book_value = fields.Monetary(string="Valor contable")
    state = fields.Selection(
        [
            ("draft", "Borrador"),
            ("open", "En servicio"),
            ("close", "Cerrado"),
        ],
        string="Estado",
        default="draft",
        required=True,
    )
    serial_number = fields.Char(string="Serie / placa")
    location = fields.Char(string="Ubicación")
    notes = fields.Text(string="Observaciones")
    active = fields.Boolean(default=True)

    bien_asegurado_ids = fields.One2many(
        "poliza.bien.asegurado", "asset_id", string="Pólizas relacionadas"
    )


class PolizaSiniestro(models.Model):
    _name = "poliza.siniestro"
    _description = "Siniestro de póliza"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "claim_date desc, id desc"

    name = fields.Char(string="Número de siniestro", required=True, copy=False, tracking=True)
    poliza_id = fields.Many2one(
        "poliza.partner", string="Póliza", required=True, ondelete="cascade", index=True, tracking=True
    )
    company_id = fields.Many2one(related="poliza_id.company_id", store=True)
    currency_id = fields.Many2one(related="poliza_id.currency_id", store=True)
    claim_date = fields.Date(string="Fecha del siniestro", required=True, default=fields.Date.today, tracking=True)
    report_date = fields.Date(string="Fecha de reporte")
    coverage_id = fields.Many2one("poliza.cobertura", string="Cobertura")
    insured_item_id = fields.Many2one("poliza.bien.asegurado", string="Bien afectado")
    description = fields.Text(string="Descripción", required=True)
    claim_amount = fields.Monetary(string="Monto reclamado")
    reserve_amount = fields.Monetary(string="Reserva")
    indemnity_amount = fields.Monetary(string="Indemnización")
    insurer_reference = fields.Char(string="Referencia de aseguradora")
    resolution_date = fields.Date(string="Fecha de resolución")
    state = fields.Selection(
        [
            ("draft", "Borrador"),
            ("reported", "Reportado"),
            ("investigation", "En investigación"),
            ("approved", "Aprobado"),
            ("paid", "Pagado"),
            ("closed", "Cerrado"),
            ("rejected", "Rechazado"),
        ],
        string="Estado",
        default="draft",
        tracking=True,
    )

    def action_report(self):
        self.write({"state": "reported", "report_date": fields.Date.today()})

    def action_investigate(self):
        self.write({"state": "investigation"})

    def action_approve(self):
        self.write({"state": "approved"})

    def action_pay(self):
        self.write({"state": "paid"})

    def action_close(self):
        self.write({"state": "closed", "resolution_date": fields.Date.today()})

    def action_reject(self):
        self.write({"state": "rejected", "resolution_date": fields.Date.today()})


class PolizaDevengamiento(models.Model):
    _name = "poliza.devengamiento"
    _description = "Devengamiento mensual de póliza"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "period_date, id"

    name = fields.Char(string="Referencia", compute="_compute_name", store=True)
    poliza_id = fields.Many2one(
        "poliza.partner", string="Póliza", required=True, ondelete="cascade", index=True, tracking=True
    )
    company_id = fields.Many2one(related="poliza_id.company_id", store=True)
    currency_id = fields.Many2one(related="poliza_id.currency_id", store=True)
    period_date = fields.Date(string="Periodo", required=True, tracking=True)
    amount = fields.Monetary(string="Importe", required=True, tracking=True)
    state = fields.Selection(
        [("draft", "Borrador"), ("posted", "Contabilizado"), ("cancelled", "Cancelado")],
        default="draft",
        tracking=True,
    )
    move_id = fields.Many2one("account.move", string="Asiento contable", readonly=True, copy=False)

    @api.depends("poliza_id.name", "period_date")
    def _compute_name(self):
        for line in self:
            period = line.period_date.strftime("%Y-%m") if line.period_date else ""
            line.name = f"{line.poliza_id.name or _('Póliza')} - {period}"

    @api.constrains("amount", "period_date")
    def _check_values(self):
        for line in self:
            if line.amount <= 0:
                raise ValidationError(_("El importe del devengamiento debe ser mayor que cero."))
            if line.period_date and line.poliza_id.fecha_inicio and line.period_date < fields.Date.start_of(line.poliza_id.fecha_inicio, "month"):
                raise ValidationError(_("El periodo del devengamiento está fuera de la vigencia de la póliza."))

    def action_post(self):
        for line in self:
            if line.state == "posted":
                continue
            policy = line.poliza_id
            if not policy.journal_devengamiento_id or not policy.account_expense_id or not policy.account_prepaid_id:
                raise UserError(
                    _(
                        "Configure en la póliza el diario, la cuenta de gasto y la cuenta de seguros pagados por anticipado."
                    )
                )
            move = self.env["account.move"].create(
                {
                    "move_type": "entry",
                    "date": line.period_date,
                    "journal_id": policy.journal_devengamiento_id.id,
                    "company_id": policy.company_id.id,
                    "ref": line.name,
                    "line_ids": [
                        (
                            0,
                            0,
                            {
                                "name": line.name,
                                "account_id": policy.account_expense_id.id,
                                "debit": line.amount,
                                "credit": 0.0,
                                "partner_id": policy.partner_id.id,
                            },
                        ),
                        (
                            0,
                            0,
                            {
                                "name": line.name,
                                "account_id": policy.account_prepaid_id.id,
                                "debit": 0.0,
                                "credit": line.amount,
                                "partner_id": policy.partner_id.id,
                            },
                        ),
                    ],
                }
            )
            move.action_post()
            line.write({"move_id": move.id, "state": "posted"})
            line.message_post(body=_("Devengamiento contabilizado en el asiento %s.") % move.name)
        return True

    def action_cancel(self):
        for line in self:
            if line.move_id and line.move_id.state == "posted":
                raise UserError(_("No se puede cancelar un devengamiento ya contabilizado."))
            line.state = "cancelled"

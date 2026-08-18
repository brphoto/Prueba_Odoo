import base64
import csv
import io
import unicodedata

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


def _header(value):
    value = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().strip().lower()
    return value.replace(" ", "_").replace("-", "_")


class CoPayrollClientImportWizard(models.TransientModel):
    _name = "l10n.co.payroll.client.import.wizard"
    _description = "Importación masiva para clientes de nómina"

    import_type = fields.Selection([
        ("employee", "Empleados"),
        ("administrator", "Administradoras PILA"),
        ("social_profile", "Perfiles PILA"),
        ("cost_center", "Centros de costo"),
        ("bank_account", "Cuentas bancarias"),
    ], string="Qué deseas cargar", required=True, default="employee")
    company_id = fields.Many2one("res.company", string="Compañía", required=True, default=lambda self: self.env.company)
    import_file = fields.Binary(string="Archivo CSV / Excel", required=True)
    filename = fields.Char(string="Nombre del archivo")
    validate_only = fields.Boolean(string="Solo validar", help="Revisa el archivo sin crear ni modificar registros.")
    state = fields.Selection([("draft", "Pendiente"), ("imported", "Importado"), ("error", "Con errores")], default="draft", required=True)
    imported_count = fields.Integer(string="Registros procesados", readonly=True)
    error_message = fields.Text(string="Resultado / errores", readonly=True)

    @api.onchange("import_type")
    def _onchange_import_type(self):
        self.error_message = False
        self.imported_count = 0

    def _read_rows(self):
        self.ensure_one()
        raw = base64.b64decode(self.import_file or b"")
        if (self.filename or "").lower().endswith(".xlsx"):
            try:
                import openpyxl
            except ImportError as exc:
                raise UserError(_("Para archivos .xlsx instala openpyxl o guarda el archivo como CSV.")) from exc
            workbook = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
            sheet = workbook.active
            values = list(sheet.values)
            if not values:
                return []
            headers = [_header(value) for value in values[0]]
            return [dict(zip(headers, row)) for row in values[1:] if any(value not in (None, "") for value in row)]
        text = raw.decode("utf-8-sig", errors="replace")
        sample = text[:4096]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=";,\t,")
        except csv.Error:
            dialect = csv.excel
            dialect.delimiter = ";"
        reader = csv.DictReader(io.StringIO(text), dialect=dialect)
        return [{_header(key): value for key, value in row.items()} for row in reader if any(value not in (None, "") for value in row.values())]

    @staticmethod
    def _value(row, *names):
        for name in names:
            value = row.get(_header(name))
            if value not in (None, ""):
                return str(value).strip()
        return False

    def _required(self, row, row_number, *names):
        value = self._value(row, *names)
        if not value:
            raise UserError(_("Fila %s: falta %s.") % (row_number, "/".join(names)))
        return value

    def _find_employee(self, identification):
        return self.env["hr.employee"].sudo().search([
            ("company_id", "=", self.company_id.id), ("identification_id", "=", identification),
        ], limit=1)

    def _apply_row(self, row, row_number):
        employee_model = self.env["hr.employee"].sudo()
        if self.import_type == "employee":
            identification = self._required(row, row_number, "identificacion", "documento", "identification_id")
            name = self._required(row, row_number, "nombre", "empleado", "name")
            employee = self._find_employee(identification)
            values = {"name": name, "identification_id": identification, "company_id": self.company_id.id}
            if employee:
                employee.write(values)
            else:
                employee_model.create(values)
            return
        if self.import_type == "administrator":
            kind = self._required(row, row_number, "tipo", "kind").lower()
            kind = {"salud": "eps", "eps": "eps", "pension": "pension", "afp": "pension", "arl": "arl", "caja": "ccf", "ccf": "ccf"}.get(kind, kind)
            if kind not in ("eps", "pension", "arl", "ccf"):
                raise UserError(_("Fila %s: tipo de administradora inválido.") % row_number)
            code = self._required(row, row_number, "codigo", "code")
            name = self._required(row, row_number, "nombre", "name")
            Administrator = self.env["l10n.co.payroll.administrator"].sudo()
            record = Administrator.search([("company_id", "=", self.company_id.id), ("kind", "=", kind), ("code", "=", code)], limit=1)
            if record:
                record.write({"name": name, "active": True})
            else:
                Administrator.create({"company_id": self.company_id.id, "kind": kind, "code": code, "name": name})
            return
        if self.import_type == "cost_center":
            code = self._required(row, row_number, "codigo", "code")
            name = self._required(row, row_number, "nombre", "name")
            Center = self.env["l10n.co.payroll.cost.center"].sudo()
            record = Center.search([("company_id", "=", self.company_id.id), ("code", "=", code)], limit=1)
            values = {"name": name, "code": code, "company_id": self.company_id.id, "active": True}
            if record:
                record.write(values)
            else:
                Center.create(values)
            return
        identification = self._required(row, row_number, "identificacion", "documento", "identification_id")
        employee = self._find_employee(identification)
        if not employee:
            raise UserError(_("Fila %s: no existe empleado con identificación %s.") % (row_number, identification))
        if self.import_type == "social_profile":
            effective_from = fields.Date.to_date(self._required(row, row_number, "vigente_desde", "effective_from", "desde"))
            mode = self._value(row, "cobertura", "coverage_mode", "modo") or "full"
            mode = {"completa": "full", "completo": "full", "manual": "manual", "externo": "manual", "no_aplica": "not_applicable", "no aplica": "not_applicable"}.get(mode.lower(), mode.lower())
            if mode not in ("full", "manual", "not_applicable"):
                raise UserError(_("Fila %s: cobertura PILA inválida.") % row_number)
            Administrator = self.env["l10n.co.payroll.administrator"].sudo()
            administrator_ids = {}
            for field_name, kinds, labels in (("eps_id", ("eps",), ("eps", "salud")), ("pension_id", ("pension",), ("pension", "afp")), ("arl_id", ("arl",), ("arl",)), ("ccf_id", ("ccf",), ("ccf", "caja"))):
                code = self._value(row, *labels)
                if code:
                    administrator_ids[field_name] = Administrator.search([("company_id", "=", self.company_id.id), ("kind", "in", kinds), ("code", "=", code)], limit=1).id
            Social = self.env["l10n.co.payroll.social"].sudo()
            Social.search([("employee_id", "=", employee.id), ("state", "=", "active")]).write({"state": "archived", "effective_to": effective_from - relativedelta(days=1)})
            values = {"name": _("Perfil PILA - %s") % employee.name, "employee_id": employee.id, "effective_from": effective_from, "state": "active", "coverage_mode": mode, "manual_reference": self._value(row, "referencia", "manual_reference", "motivo"), **administrator_ids}
            if mode == "full" and not all(administrator_ids.get(field) for field in ("eps_id", "pension_id", "arl_id", "ccf_id")):
                values.update({"require_eps": bool(administrator_ids.get("eps_id")), "require_pension": bool(administrator_ids.get("pension_id")), "require_arl": bool(administrator_ids.get("arl_id")), "require_ccf": bool(administrator_ids.get("ccf_id"))})
            Social.create(values)
            return
        account_number = self._required(row, row_number, "cuenta", "numero_cuenta", "acc_number")
        partner = employee.address_home_id or employee.work_contact_id or (employee.user_id.partner_id if employee.user_id else False)
        if not partner:
            raise UserError(_("Fila %s: el empleado no tiene un contacto para asociar la cuenta bancaria.") % row_number)
        bank_name = self._value(row, "banco", "bank")
        bank = self.env["res.bank"].sudo().search([("name", "=", bank_name)], limit=1) if bank_name else False
        if bank_name and not bank:
            bank = self.env["res.bank"].sudo().create({"name": bank_name})
        existing = self.env["res.partner.bank"].sudo().search([("partner_id", "=", partner.id), ("acc_number", "=", account_number)], limit=1)
        if not existing:
            self.env["res.partner.bank"].sudo().create({"acc_number": account_number, "partner_id": partner.id, "bank_id": bank.id if bank else False})

    def action_import(self):
        self.ensure_one()
        try:
            rows = self._read_rows()
            if not rows:
                raise UserError(_("El archivo no contiene filas."))
            if len(rows) > 2000:
                raise UserError(_("El archivo supera el límite de 2.000 filas por carga."))
            with self.env.cr.savepoint():
                for row_number, row in enumerate(rows, 2):
                    if not self.validate_only:
                        self._apply_row(row, row_number)
                    else:
                        # Reuse all validations without changing the database.
                        required = {
                            "employee": ("identificacion", "nombre"),
                            "administrator": ("tipo", "codigo", "nombre"),
                            "cost_center": ("codigo", "nombre"),
                            "social_profile": ("identificacion", "vigente_desde"),
                            "bank_account": ("identificacion", "cuenta"),
                        }[self.import_type]
                        for key in required:
                            self._required(row, row_number, key)
                self.write({"state": "imported", "imported_count": len(rows), "error_message": _("Archivo válido. %s registros procesados%s.") % (len(rows), _(" (solo validación)") if self.validate_only else "")})
        except Exception as exc:
            self.write({"state": "error", "imported_count": 0, "error_message": str(exc)})
        return True

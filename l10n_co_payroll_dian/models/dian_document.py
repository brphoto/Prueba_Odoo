import base64
import csv
import hashlib
import io
import json
import re
import unicodedata
import zipfile
from datetime import datetime, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .cune_calculator import build_cune_seed, calculate_cune
from .dian_soap_client import DianSoapClient, DianSoapError
from .firma_digital import sign_xml
from .xml_builder_nomina import build_nomina_xml
from .xml_validator import validate_xml


class CoPayrollDianDocument(models.Model):
    _name = "l10n.co.payroll.dian.document"
    _description = "Documento soporte de nómina electrónica DIAN"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"
    _check_company_auto = True

    name = fields.Char(string="Número DIAN", copy=False, readonly=True, index=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    period_id = fields.Many2one("l10n.co.payroll.period", required=True, ondelete="restrict", index=True)
    period_line_id = fields.Many2one("l10n.co.payroll.period.line", required=True, ondelete="restrict", index=True)
    employee_id = fields.Many2one("hr.employee", related="period_line_id.employee_id", store=True, readonly=True)
    is_adjustment = fields.Boolean(string="Nota de ajuste", default=False, copy=False)
    tipo_nota = fields.Selection([("1", "Reemplazar"), ("2", "Eliminar")], string="Tipo de nota", default="1")
    predecessor_id = fields.Many2one("l10n.co.payroll.dian.document", string="Documento predecesor", copy=False)
    state = fields.Selection([
        ("draft", "Borrador"),
        ("generated", "Generado"),
        ("validated", "Validado localmente"),
        ("pending", "Pendiente DIAN"),
        ("accepted", "Aceptado"),
        ("rejected", "Rechazado"),
        ("error", "Error"),
        ("cancelled", "Cancelado"),
    ], string="Estado", default="draft", required=True, copy=False, tracking=True, index=True)
    prefix = fields.Char(string="Prefijo", copy=False, readonly=True)
    consecutive = fields.Char(string="Consecutivo", copy=False, readonly=True)
    cune = fields.Char(string="CUNE", copy=False, readonly=True, index=True)
    cune_seed = fields.Text(string="Semilla CUNE", copy=False, readonly=True)
    xml_filename = fields.Char(string="Archivo XML", copy=False, readonly=True)
    xml_file = fields.Binary(string="XML firmado", copy=False, readonly=True, attachment=True)
    zip_filename = fields.Char(string="Archivo ZIP", copy=False, readonly=True)
    zip_file = fields.Binary(string="ZIP enviado", copy=False, readonly=True, attachment=True)
    application_response_filename = fields.Char(string="Respuesta DIAN", copy=False, readonly=True)
    application_response_file = fields.Binary(string="ApplicationResponse", copy=False, readonly=True, attachment=True)
    request_log = fields.Text(string="Solicitud SOAP", copy=False, readonly=True)
    response_log = fields.Text(string="Respuesta SOAP", copy=False, readonly=True)
    xml_validation_errors = fields.Text(string="Errores de validación XML", copy=False, readonly=True)
    status_code = fields.Char(string="Código DIAN", copy=False, readonly=True)
    status_message = fields.Text(string="Mensaje DIAN", copy=False, readonly=True)
    zip_key = fields.Char(string="ZipKey / Track ID", copy=False, readonly=True, index=True)
    xml_document_key = fields.Char(string="XmlDocumentKey", copy=False, readonly=True, index=True)
    attempt_count = fields.Integer(string="Intentos", copy=False, readonly=True)
    generated_by = fields.Many2one("res.users", string="Generado por", readonly=True, copy=False)
    generated_at = fields.Datetime(string="Fecha de generación", readonly=True, copy=False)
    sent_by = fields.Many2one("res.users", string="Enviado por", readonly=True, copy=False)
    sent_at = fields.Datetime(string="Fecha de envío", readonly=True, copy=False)
    last_checked_at = fields.Datetime(string="Última consulta", readonly=True, copy=False)
    error_message = fields.Text(string="Detalle del error", copy=False, readonly=True)
    error_category = fields.Selection([
        ("data", "Datos"), ("xml", "XML/XSD"), ("signature", "Firma"),
        ("certificate", "Certificado"), ("soap", "SOAP/DIAN"), ("network", "Red"),
    ], string="Categoría del error", copy=False, readonly=True)
    reconciliation_difference = fields.Monetary(string="Diferencia de conciliación", currency_field="currency_id", copy=False, readonly=True)
    last_query_operation = fields.Selection([
        ("get_status", "GetStatus por CUNE"), ("get_status_zip", "GetStatusZip por ZipKey"),
    ], string="Operación de consulta", copy=False, readonly=True)
    submission_environment = fields.Selection(
        [("1", "Producción"), ("2", "Habilitación")],
        string="Ambiente de envío", copy=False, readonly=True,
    )
    preflight_state = fields.Selection([
        ("pending", "Pendiente"), ("ok", "Listo"), ("warning", "Con advertencias"), ("error", "Con errores"),
    ], string="Prevalidación", default="pending", copy=False, readonly=True, tracking=True)
    preflight_message = fields.Text(string="Resultado de prevalidación", copy=False, readonly=True)
    preflight_at = fields.Datetime(string="Fecha de prevalidación", copy=False, readonly=True)
    retry_count = fields.Integer(string="Reintentos", copy=False, readonly=True)
    next_retry_at = fields.Datetime(string="Próximo reintento", copy=False, readonly=True)
    last_retry_at = fields.Datetime(string="Último reintento", copy=False, readonly=True)
    approval_state = fields.Selection([
        ("not_required", "No requerida"), ("pending", "Pendiente"), ("first_approved", "Primera aprobación"),
        ("approved", "Aprobada"), ("rejected", "Rechazada"),
    ], string="Aprobación de envío", default="not_required", copy=False, readonly=True, tracking=True)
    approval_by = fields.Many2one("res.users", string="Aprobado por", copy=False, readonly=True)
    approval_at = fields.Datetime(string="Fecha de aprobación", copy=False, readonly=True)
    second_approval_by = fields.Many2one("res.users", string="Segunda aprobación", copy=False, readonly=True)
    second_approval_at = fields.Datetime(string="Fecha segunda aprobación", copy=False, readonly=True)
    source_gross = fields.Monetary(string="Devengado fuente", currency_field="currency_id", compute="_compute_reconciliation")
    source_deductions = fields.Monetary(string="Deducciones fuente", currency_field="currency_id", compute="_compute_reconciliation")
    source_net = fields.Monetary(string="Neto fuente", currency_field="currency_id", compute="_compute_reconciliation")
    transmitted_net = fields.Monetary(string="Neto transmitido", currency_field="currency_id", compute="_compute_reconciliation")
    mapping_summary = fields.Char(string="Mapeo DIAN", compute="_compute_mapping_summary")
    attention_level = fields.Selection([
        ("success", "Correcto"), ("info", "Información"), ("warning", "Atención"), ("danger", "Crítico"),
    ], string="Nivel de atención", compute="_compute_attention", store=True)
    attention_message = fields.Char(string="Aviso operativo", compute="_compute_attention", store=True)
    is_stale_pending = fields.Boolean(string="Pendiente antiguo", compute="_compute_attention", store=True)
    attempt_ids = fields.One2many("l10n.co.payroll.dian.attempt", "document_id", string="Trazabilidad", readonly=True)
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)

    @api.depends("period_line_id", "period_line_id.gross_wage", "period_line_id.deduction_total", "reconciliation_difference")
    def _compute_reconciliation(self):
        for document in self:
            line = document.period_line_id
            document.source_gross = line.gross_wage if line else 0.0
            document.source_deductions = line.deduction_total if line else 0.0
            document.source_net = document.source_gross - document.source_deductions
            document.transmitted_net = document.source_net - (document.reconciliation_difference or 0.0)

    @api.depends("period_id", "period_id.parameter_id", "period_line_id")
    def _compute_mapping_summary(self):
        for document in self:
            if not document.period_id or not document.period_id.parameter_id:
                document.mapping_summary = _("Sin versión legal")
                continue
            mappings = self.env["l10n.co.payroll.rule.mapping"].search([
                ("company_id", "=", document.company_id.id),
                ("parameter_id", "=", document.period_id.parameter_id.id),
                ("active", "=", True),
            ])
            mapped = len(mappings.filtered("dian_concept"))
            document.mapping_summary = _("%s reglas DIAN configuradas") % mapped

    @api.depends("state", "preflight_state", "error_message", "status_message", "last_checked_at", "sent_at", "company_id.co_dian_pending_alert_hours")
    def _compute_attention(self):
        now = fields.Datetime.now()
        for document in self:
            level = "info"
            message = _("Pendiente de revisión")
            stale = False
            if document.state == "accepted":
                level, message = "success", _("Aceptado por la DIAN")
            elif document.state == "rejected":
                level, message = "danger", document.status_message or _("Rechazado por la DIAN")
            elif document.state == "error":
                level, message = "danger", document.error_message or _("Revisar el error del documento")
            elif document.state == "pending":
                sent_at = document.sent_at
                stale = bool(sent_at and sent_at <= now - timedelta(hours=max(document.company_id.co_dian_pending_alert_hours, 1)))
                level = "danger" if stale else "warning"
                message = _("Sin respuesta DIAN desde hace más de %s horas") % document.company_id.co_dian_pending_alert_hours if stale else _("Esperando respuesta de la DIAN")
            elif document.preflight_state == "error":
                level, message = "danger", document.preflight_message or _("Corregir prevalidación")
            elif document.preflight_state == "warning":
                level, message = "warning", document.preflight_message or _("Revisar advertencias")
            elif document.state in ("validated", "generated"):
                level, message = "info", _("Listo para transmitir")
            document.attention_level = level
            document.attention_message = message
            document.is_stale_pending = stale

    _co_dian_document_number_unique = models.Constraint(
        "unique(company_id, name)",
        "El número de nómina electrónica debe ser único por compañía.",
    )

    @api.constrains("period_line_id", "company_id")
    def _check_company_line(self):
        for record in self:
            if record.period_line_id.company_id != record.company_id:
                raise ValidationError(_("El resumen de nómina y el documento DIAN deben pertenecer a la misma compañía."))

    @staticmethod
    def _digits(value):
        return re.sub(r"\D+", "", str(value or ""))

    @staticmethod
    def _normalize(value):
        value = unicodedata.normalize("NFKD", str(value or ""))
        return "".join(char for char in value if not unicodedata.combining(char)).lower()

    @classmethod
    def _split_name(cls, value):
        parts = str(value or "").split()
        if len(parts) >= 4:
            return parts[0], parts[1], parts[2], " ".join(parts[3:])
        if len(parts) == 3:
            return parts[0], parts[1], parts[2], ""
        if len(parts) == 2:
            return parts[0], "", parts[1], ""
        return parts[0] if parts else "Empleado", "", "", ""

    @staticmethod
    def _verification_digit(vat):
        digits = re.sub(r"\D+", "", str(vat or ""))
        if not digits:
            return "0"
        weights = (71, 67, 59, 53, 47, 43, 41, 37, 29, 23, 19, 17, 13, 7, 3)
        total = sum(int(digit) * weights[-len(digits) + index] for index, digit in enumerate(digits))
        remainder = total % 11
        return str(remainder if remainder < 2 else 11 - remainder)

    def _company_tax_id(self):
        raw = str(self.company_id.vat or "").strip()
        if "-" in raw:
            nit, supplied_digit = raw.rsplit("-", 1)
            nit = self._digits(nit)
            if nit:
                return nit, self._digits(supplied_digit)[:1] or self._verification_digit(nit)
        nit = self._digits(raw)
        return nit, self._verification_digit(nit)

    @staticmethod
    def _date_text(value, fallback):
        return fields.Date.to_string(value or fallback)

    def _company_location(self):
        company = self.company_id
        partner = company.partner_id
        country = getattr(partner.country_id, "code", False) or "CO"
        department = getattr(partner.state_id, "code", False) or "11"
        city = getattr(partner, "city", False) or "11001"
        return country, department, city, partner.street or "NA"

    def _source_amount(self, keys):
        wanted = {self._normalize(key) for key in keys}
        total = 0.0
        for payslip in self.period_line_id.source_payslip_ids:
            for line in payslip.line_ids:
                values = [getattr(line, "code", False), getattr(line, "name", False), getattr(getattr(line, "salary_rule_id", False), "code", False)]
                normalized = {self._normalize(value) for value in values if value}
                if normalized.intersection(wanted):
                    total += line.total or 0.0
        return abs(total)

    def _explicit_dian_totals(self):
        """Read DIAN concepts from configured payroll-rule mappings.

        The heuristic name matching remains available for backwards compatibility,
        but an explicit mapping can override every supported concept and exposes
        unmapped payroll rules before transmission.
        """
        totals = {"devengados": {}, "deducciones": {}, "unmapped": []}
        parameter = self.period_id.parameter_id
        if not parameter:
            return totals
        mappings = self.env["l10n.co.payroll.rule.mapping"].search([
            ("company_id", "=", self.company_id.id),
            ("parameter_id", "=", parameter.id),
            ("active", "=", True),
            ("dian_concept", "!=", False),
        ])
        by_code = {mapping.code.upper(): mapping for mapping in mappings if mapping.code}
        for payslip in self.period_line_id.source_payslip_ids:
            for line in payslip.line_ids:
                salary_rule = getattr(line, "salary_rule_id", False)
                native_rule = getattr(salary_rule, "co_payroll_rule_id", False)
                code = getattr(native_rule, "code", False) or getattr(salary_rule, "code", False)
                if not code or not line.total:
                    continue
                mapping = by_code.get(str(code).upper())
                if not mapping:
                    totals["unmapped"].append(str(code).upper())
                    continue
                target = "deducciones" if mapping.concept_type in ("deduction", "employee_contribution") else "devengados"
                key = mapping.dian_concept
                totals[target][key] = totals[target].get(key, 0.0) + abs(line.total or 0.0)
        totals["unmapped"] = sorted(set(totals["unmapped"]))
        return totals

    def _xml_categories(self):
        line = self.period_line_id
        def amount(*keys):
            return self._source_amount(keys)

        vacation = amount("vacaciones", "vacacion")
        prima = amount("prima", "primas", "prima_servicios")
        incapacity_common = amount("incapacidad", "incapacidad_comun")
        dev = {
            "basico": line.basic_wage,
            "auxilio_transporte": line.transport_base,
            "viatico_manu_aloj_s": amount("viatico_s", "viaticos salariales"),
            "viatico_manu_aloj_ns": amount("viatico_ns", "viaticos no salariales"),
            "primas_pago": prima,
            "primas_cantidad": 30 if prima else 0,
            "primas_pago_ns": amount("prima_no_salarial"),
            "vacaciones_pago": vacation,
            "vacaciones_cantidad": int(line.worked_days) if vacation else 0,
            "cesantias_pago": amount("cesantias", "cesantia"),
            "cesantias_porcentaje": 8.33 if amount("cesantias", "cesantia") else 0.0,
            "intereses_cesantias": amount("intereses_cesantias", "intereses cesantias"),
            "comision": amount("comision", "comisiones"),
            "dotacion": amount("dotacion"),
            "apoyo_sost": amount("apoyo_sostenimiento", "apoyo sost"),
            "teletrabajo": amount("teletrabajo"),
            "bonif_retiro": amount("bonificacion_retiro", "bonif retiro"),
            "indemnizacion": amount("indemnizacion"),
            "reintegro": amount("reintegro"),
            "auxilio_s": amount("auxilio_salarial", "auxilio salarial"),
            "auxilio_ns": amount("auxilio_no_salarial", "auxilio no salarial"),
            "licencia_mp_cantidad": 1 if amount("licencia_maternidad", "licencia mp") else 0,
            "licencia_mp_pago": amount("licencia_maternidad", "licencia mp"),
            "licencia_r_cantidad": 1 if amount("licencia_remunerada", "licencia r") else 0,
            "licencia_r_pago": amount("licencia_remunerada", "licencia r"),
            "licencia_nr_cantidad": 1 if amount("licencia_no_remunerada", "licencia nr") else 0,
            "incapacidad_comun_cantidad": 1 if incapacity_common else 0,
            "incapacidad_comun_pago": incapacity_common,
            "incapacidad_profesional_cantidad": 1 if amount("incapacidad_profesional") else 0,
            "incapacidad_profesional_pago": amount("incapacidad_profesional"),
            "incapacidad_laboral_cantidad": 1 if amount("incapacidad_laboral") else 0,
            "incapacidad_laboral_pago": amount("incapacidad_laboral"),
            "retencion_fuente": 0.0,
            "hed_cantidad": line.overtime_day_hours,
            "hed_pago": amount("hed", "hora extra diurna"),
            "hen_cantidad": line.overtime_night_hours,
            "hen_pago": amount("hen", "hora extra nocturna"),
            "hrn_pago": amount("hrn", "recargo nocturno"),
            "heddf_pago": amount("heddf", "hora extra diurna festiva"),
            "hrddf_pago": amount("hrddf", "recargo diurno festivo"),
            "hendf_pago": amount("hendf", "hora extra nocturna festiva"),
            "hrndf_pago": amount("hrndf", "recargo nocturno festivo"),
        }
        ded = {
            "salud_porcentaje": 4.0 if line.health_employee else 0.0,
            "salud": line.health_employee,
            "pension_porcentaje": 4.0 if line.pension_employee else 0.0,
            "pension": line.pension_employee,
            "fsp_porcentaje": line.solidarity_rate or 0.0,
            "fsp": line.solidarity_employee,
            "retencion_fuente": amount("retencion", "retencion_fuente", "retefuente"),
            "afc": amount("afc"),
            "cooperativa": amount("cooperativa"),
            "sindicato": amount("sindicato"),
            "sancion": amount("sancion"),
            "libranza": amount("libranza"),
            "pension_voluntaria": amount("pension voluntaria"),
            "plan_complementarios": amount("plan complementario", "plan complementarios"),
            "educacion": amount("educacion"),
            "reintegro": amount("reintegro deduccion"),
            "embargo_fiscal": line.embargo_deduction,
            "deuda": line.loan_deduction,
        }
        explicit = self._explicit_dian_totals()
        dev.update(explicit["devengados"])
        ded.update(explicit["deducciones"])
        return {"devengados": dev, "deducciones": ded, "unmapped": explicit["unmapped"]}

    def _allocate_number(self):
        if self.name:
            return
        number = self.env["ir.sequence"].next_by_code("l10n.co.payroll.dian.document")
        if not number:
            raise UserError(_("No existe una secuencia para nómina electrónica DIAN."))
        match = re.match(r"^(.*?)(\d+)$", number)
        prefix, consecutive = (match.group(1), match.group(2)) if match else ("", number)
        self.write({"name": number, "prefix": prefix, "consecutive": consecutive})

    def _build_context(self):
        self.ensure_one()
        company = self.company_id
        line = self.period_line_id
        period = self.period_id
        profile = line.social_profile_id
        employee = line.employee_id
        partner = getattr(employee, "work_contact_id", False) or getattr(employee, "address_home_id", False) or getattr(employee, "address_id", False)
        identification = self._digits(getattr(employee, "identification_id", False) or getattr(partner, "vat", False))
        if not identification:
            raise UserError(_("El empleado %s no tiene número de identificación documental.") % employee.display_name)
        if not self.name:
            self._allocate_number()
        now = fields.Datetime.context_timestamp(self, fields.Datetime.now())
        fecha_gen = now.date().isoformat()
        hora_gen = now.strftime("%H:%M:%S-05:00")
        categories = self._xml_categories()
        dev = categories["devengados"]
        ded = categories["deducciones"]
        dev_amount_keys = {
            "basico", "auxilio_transporte", "viatico_manu_aloj_s", "viatico_manu_aloj_ns",
            "primas_pago", "primas_pago_ns", "vacaciones_pago", "cesantias_pago", "intereses_cesantias",
            "comision", "dotacion", "apoyo_sost", "teletrabajo", "bonif_retiro", "indemnizacion",
            "reintegro", "auxilio_s", "auxilio_ns", "licencia_mp_pago", "licencia_r_pago",
            "incapacidad_comun_pago", "incapacidad_profesional_pago", "incapacidad_laboral_pago",
            "hed_pago", "hen_pago", "hrn_pago", "heddf_pago", "hrddf_pago", "hendf_pago", "hrndf_pago",
        }
        mapped_dev = sum(float(dev.get(key) or 0.0) for key in dev_amount_keys)
        dev_total = round(max(float(line.gross_wage or 0.0), mapped_dev), 2)
        if dev_total - mapped_dev > 0.01:
            dev["otro_concepto_descripcion"] = "Otros conceptos de nómina"
            dev["otro_concepto_s"] = round(dev_total - mapped_dev, 2)
        ded_amount_keys = {
            "salud", "pension", "fsp", "fsp_sub", "retencion_fuente", "afc", "cooperativa",
            "embargo_fiscal", "plan_complementarios", "educacion", "reintegro", "deuda",
        }
        mapped_ded = sum(float(ded.get(key) or 0.0) for key in ded_amount_keys)
        ded_total = round(max(float(line.deduction_total or 0.0), mapped_ded), 2)
        if ded_total - mapped_ded > 0.01:
            ded["otra_deduccion"] = round(ded_total - mapped_ded, 2)
        comprobante = round(dev_total - ded_total, 2)
        vat, verification_digit = self._company_tax_id()
        if not vat:
            raise UserError(_("Configura el NIT de la compañía antes de generar nómina electrónica."))
        tipo_xml = "103" if self.is_adjustment else "102"
        cune_values = {
            "NumeroCompleto": self.name,
            "FechaGen": fecha_gen,
            "HoraGen": hora_gen,
            "DevengadosTotal": dev_total,
            "DeduccionesTotal": ded_total,
            "ComprobanteTotal": comprobante,
            "EmpleadorNIT": vat,
            "TrabajadorID": identification,
            "TipoXML": tipo_xml,
            "SoftwarePIN": company.co_dian_software_pin or "",
            "Ambiente": company.co_dian_environment or "2",
        }
        cune = calculate_cune(cune_values)
        country, department, city, address = self._company_location()
        first_last, second_last, first_name, other_names = self._split_name(getattr(partner, "name", False) or employee.name)
        worker_type = str(getattr(profile, "contributor_type", False) or line.pila_type or "01").zfill(2)
        worker_subtype = str(getattr(profile, "contributor_subtype", False) or line.pila_subtype or "0").zfill(2)
        salary_mode = getattr(profile, "salary_mode", False) or line.salary_mode or "ordinary"
        contract = line.contract_id
        contract_date = getattr(contract, "date_start", False) or period.date_from
        tipo_documento = {"CC": "13", "CE": "22", "NIT": "31", "TI": "12", "PA": "41", "PPT": "47"}.get(str(getattr(profile, "identification_type", "CC")).upper(), "13")
        security_code = hashlib.sha384(((company.co_dian_software_id or "") + (company.co_dian_software_pin or "") + self.name).encode("utf-8")).hexdigest()
        payload = {
            "NIT": vat,
            "DV": verification_digit,
            "RazonSocial": company.name,
            "PaisEmpleador": country,
            "DepartamentoEstadoEmpleador": department,
            "MunicipioCiudadEmpleador": city,
            "DireccionEmpleador": address,
            "paisgeneracion": country,
            "departamentoestado": department,
            "municipiociudad": city,
            "PeriodoNomina": "5" if period.period_type == "monthly" else "4",
            "TipoMoneda": "COP",
        }
        if self.is_adjustment and self.predecessor_id:
            payload.update({
                "NumeroPred": self.predecessor_id.name,
                "CUNEPred": self.predecessor_id.cune,
                "FechaGenPred": fields.Date.to_string(self.predecessor_id.generated_at.date()) if self.predecessor_id.generated_at else fields.Date.to_string(period.date_from),
            })
        record = {
            "fecha_ingreso": contract_date,
            "fecha_retiro": getattr(contract, "date_end", False),
            "fecha_liquidacion_inicio": period.date_from,
            "fecha_liquidacion_fin": period.date_to,
            "tiempo_laborado": min(max(int(line.worked_days or 0), 0), 30),
            "codigo_trabajador": identification,
            "tipo_trabajador": worker_type,
            "sub_tipo_trabajador": worker_subtype,
            "alto_riesgo_pension": "true" if getattr(profile, "risk_class", "I") in ("IV", "V") else "false",
            "tipo_documento": tipo_documento,
            "numero_documento": identification,
            "primer_apellido": first_last,
            "segundo_apellido": second_last,
            "primer_nombre": first_name,
            "otros_nombres": other_names,
            "lugar_trabajo_pais": country,
            "lugar_trabajo_departamento": department,
            "lugar_trabajo_municipio": city,
            "lugar_trabajo_direccion": address,
            "salario_integral": "true" if salary_mode == "integral" else "false",
            "tipo_contrato": "2",
            "sueldo": line.basic_wage or getattr(contract, "wage", 0.0),
            "forma_pago": "1",
            "metodo_pago": "10",
            "banco": "",
            "tipo_cuenta": "",
            "numero_cuenta": "",
            "fecha_pago": period.payment_date or period.date_to,
            "dias_trabajados": min(max(int(line.worked_days or 0), 0), 30),
        }
        data = {
            "payload": payload,
            "record": record,
            "xml_categories": {"devengados": dev, "deducciones": ded},
            "is_adjustment": self.is_adjustment,
            "tipo_nota": self.tipo_nota or "1",
            "fecha_ingreso": contract_date,
            "fecha_liquidacion_inicio": period.date_from,
            "fecha_liquidacion_fin": period.date_to,
            "tiempo_laborado": record["tiempo_laborado"],
            "fecha_retiro": record["fecha_retiro"],
            "meta": {"fecha_gen": fecha_gen, "hora_gen": hora_gen, "ambiente": company.co_dian_environment or "2", "prefix": self.prefix or "NOM", "consecutivo": self.consecutive or self.name, "numero_completo": self.name},
            "codigo_trabajador": identification,
            "software_id": company.co_dian_software_id or "",
            "software_security_code": security_code,
            "cune": cune,
            "cune_seed": build_cune_seed(cune_values),
            "codigo_qr": f"NumNIE={self.name} FecNIE={fecha_gen} HorNIE={hora_gen} NitFe={vat} DocEmp={identification} ValDev={dev_total:.2f} ValDed={ded_total:.2f} ValTolNE={comprobante:.2f} CUNE={cune}",
            "tipo_xml": tipo_xml,
            "tipo_trabajador": worker_type,
            "sub_tipo_trabajador": worker_subtype,
            "alto_riesgo_pension": record["alto_riesgo_pension"],
            "tipo_documento": tipo_documento,
            "numero_documento": identification,
            "primer_apellido": first_last,
            "segundo_apellido": second_last,
            "primer_nombre": first_name,
            "otros_nombres": other_names,
            "lugar_trabajo_pais": country,
            "lugar_trabajo_departamento": department,
            "lugar_trabajo_municipio": city,
            "lugar_trabajo_direccion": address,
            "salario_integral": record["salario_integral"],
            "tipo_contrato": record["tipo_contrato"],
            "sueldo": record["sueldo"],
            "forma_pago": record["forma_pago"],
            "metodo_pago": record["metodo_pago"],
            "banco": record["banco"],
            "tipo_cuenta": record["tipo_cuenta"],
            "numero_cuenta": record["numero_cuenta"],
            "fecha_pago": record["fecha_pago"],
            "dias_trabajados": record["dias_trabajados"],
            "trm": 0,
            "totals": {"devengados_total": dev_total, "deducciones_total": ded_total, "comprobante_total": comprobante},
            "source_reconciliation_difference": round((float(line.gross_wage or 0.0) - float(line.deduction_total or 0.0)) - comprobante, 2),
        }
        return data

    def _zip_bytes(self, xml_bytes):
        xml_filename = f"{self.name}.xml"
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(xml_filename, xml_bytes)
        return output.getvalue(), xml_filename

    def _validate_context(self, data):
        errors = []
        payload = data.get("payload", {})
        record = data.get("record", {})
        totals = data.get("totals", {})
        number = str(data.get("meta", {}).get("numero_completo") or "")
        identification = str(data.get("numero_documento") or "")
        if not re.fullmatch(r"[A-Za-z0-9]+", number):
            errors.append(_("El número DIAN solo puede contener letras y números."))
        if not identification.isdigit():
            errors.append(_("La identificación del trabajador debe contener solo dígitos."))
        if not str(payload.get("NIT") or "").isdigit():
            errors.append(_("El NIT del empleador debe contener solo dígitos."))
        if not data.get("cune") or len(data["cune"]) != 96:
            errors.append(_("El CUNE debe tener 96 caracteres SHA-384."))
        if any(float(totals.get(key) or 0.0) < 0 for key in ("devengados_total", "deducciones_total", "comprobante_total")):
            errors.append(_("Los totales DIAN no pueden ser negativos."))
        expected = round(float(totals.get("devengados_total") or 0.0) - float(totals.get("deducciones_total") or 0.0), 2)
        actual = round(float(totals.get("comprobante_total") or 0.0), 2)
        if expected != actual:
            errors.append(_("El comprobante total no coincide con devengados menos deducciones."))
        start = fields.Date.to_date(record.get("fecha_liquidacion_inicio"))
        end = fields.Date.to_date(record.get("fecha_liquidacion_fin"))
        if start and end and start > end:
            errors.append(_("La fecha inicial de liquidación no puede ser posterior a la fecha final."))
        if not record.get("fecha_pago"):
            errors.append(_("El documento requiere fecha de pago."))
        if float(record.get("dias_trabajados") or 0.0) <= 0:
            errors.append(_("El documento requiere días trabajados mayores que cero."))
        unmapped = data.get("xml_categories", {}).get("unmapped", [])
        if self.company_id.co_dian_require_explicit_mapping and unmapped:
            errors.append(_("Reglas salariales sin mapeo DIAN explícito: %s") % ", ".join(unmapped[:20]))
        return errors

    def _log_attempt(self, operation, status, message="", detail=None, response=None):
        self.env["l10n.co.payroll.dian.attempt"].sudo().create({
            "document_id": self.id,
            "operation": operation,
            "status": status,
            "message": message,
            "technical_detail": json.dumps(detail or {}, ensure_ascii=False, default=str) if isinstance(detail, (dict, list)) else (detail or ""),
            "response": json.dumps(response or {}, ensure_ascii=False, default=str) if isinstance(response, (dict, list)) else (response or ""),
            "cune": self.cune,
            "zip_key": self.zip_key,
        })

    @staticmethod
    def _classify_error(error):
        text = str(error or "").lower()
        if "certificado" in text or "pkcs" in text or "private key" in text:
            return "certificate"
        if "firma" in text or "signature" in text or "xades" in text:
            return "signature"
        if "xsd" in text or "xml" in text:
            return "xml"
        if "soap" in text or "dian" in text or "status" in text:
            return "soap"
        if "timeout" in text or "connection" in text or "red" in text:
            return "network"
        return "data"

    def action_prevalidate(self):
        """Run business checks without signing or transmitting the XML."""
        for document in self:
            try:
                data = document._build_context()
                errors = document._validate_context(data)
                if errors:
                    document.write({
                        "preflight_state": "error",
                        "preflight_message": "\n".join(errors),
                        "preflight_at": fields.Datetime.now(),
                    })
                else:
                    document.write({
                        "preflight_state": "ok",
                        "preflight_message": _("Los datos están listos para generar el XML."),
                        "preflight_at": fields.Datetime.now(),
                    })
            except Exception as exc:
                document.write({
                    "preflight_state": "error",
                    "preflight_message": str(exc),
                    "preflight_at": fields.Datetime.now(),
                })
        return {"type": "ir.actions.client", "tag": "reload"}

    def _prepare_send_approval(self):
        self.ensure_one()
        mode = self.company_id.co_dian_approval_mode
        if mode == "none":
            if self.approval_state != "not_required":
                self.write({"approval_state": "not_required", "approval_by": False, "approval_at": False, "second_approval_by": False, "second_approval_at": False})
            return
        if self.approval_state == "not_required":
            self.write({"approval_state": "pending"})
        if self.approval_state != "approved":
            raise UserError(_("El documento requiere aprobación antes de enviarse a la DIAN."))

    def action_approve_send(self):
        if not (self.env.su or self.env.user._is_admin() or self.env.user.has_group("l10n_co_payroll.group_co_payroll_manager")):
            raise UserError(_("Solo un supervisor puede aprobar el envío DIAN."))
        for document in self:
            mode = document.company_id.co_dian_approval_mode
            if mode == "none":
                raise UserError(_("La compañía no tiene aprobación de envío configurada."))
            if document.state not in ("validated", "generated"):
                raise UserError(_("Solo se pueden aprobar documentos validados localmente."))
            if document.approval_state in ("pending", "rejected", "not_required"):
                document.write({"approval_state": "approved" if mode == "single" else "first_approved", "approval_by": self.env.user.id, "approval_at": fields.Datetime.now()})
            elif mode == "double" and document.approval_state == "first_approved":
                if document.approval_by == self.env.user:
                    raise UserError(_("La segunda aprobación debe realizarla un supervisor diferente."))
                document.write({"approval_state": "approved", "second_approval_by": self.env.user.id, "second_approval_at": fields.Datetime.now()})
            else:
                raise UserError(_("El documento ya tiene la aprobación completa."))
            document._log_attempt("approve", "success", _("Aprobación de envío registrada."))
        return {"type": "ir.actions.client", "tag": "reload"}

    def action_generate(self):
        for document in self:
            document.ensure_one()
            if not document.company_id.co_dian_payroll_enabled:
                raise UserError(_("Activa primero la nómina electrónica DIAN en la compañía."))
            if document.period_id.state not in ("ready", "closed"):
                raise UserError(_("El periodo debe estar preparado o cerrado antes de generar el documento DIAN."))
            if not document.company_id.co_dian_software_id or not document.company_id.co_dian_software_pin:
                raise UserError(_("Configura el ID y PIN del software DIAN."))
            try:
                data = document._build_context()
                validation_errors = document._validate_context(data)
                if validation_errors:
                    raise UserError(_("Los datos no están listos para DIAN:\n%s") % "\n".join(validation_errors))
                unsigned = build_nomina_xml(data)
                # El XSD exige contenido dentro de ExtensionContent; ese contenido
                # es precisamente la firma XAdES que se agrega en el siguiente paso.
                # Por eso la validación contra XSD se realiza sobre el XML firmado.
                material = document.company_id._co_dian_signing_material()
                if not material:
                    raise UserError(_("Configura el certificado digital antes de generar el XML firmado."))
                signed = sign_xml(unsigned, binary_file=material.get("certificate_data"), password=material.get("password"), pem_certificate=material.get("pem_certificate"), pem_key=material.get("pem_key"))
                valid, errors = validate_xml(signed, document.is_adjustment)
                if not valid:
                    raise UserError(_("El XML firmado no cumple el XSD DIAN:\n%s") % "\n".join(errors))
                zip_bytes, xml_filename = document._zip_bytes(signed)
                document.write({
                    "xml_file": base64.b64encode(signed), "xml_filename": xml_filename,
                    "zip_file": base64.b64encode(zip_bytes), "zip_filename": f"{document.name}.zip",
                    "cune": data["cune"], "cune_seed": data["cune_seed"],
                    "state": "validated", "generated_by": self.env.user.id, "generated_at": fields.Datetime.now(),
                    "xml_validation_errors": False, "error_message": False,
                    "error_category": False, "reconciliation_difference": data.get("source_reconciliation_difference", 0.0),
                    "preflight_state": "ok", "preflight_message": _("Validación de negocio y XML completada."),
                    "preflight_at": fields.Datetime.now(),
                })
                document._log_attempt("generate", "success", _("XML firmado y validado localmente."))
            except Exception as exc:
                document.write({"state": "error", "error_message": str(exc), "error_category": document._classify_error(exc), "xml_validation_errors": str(exc)})
                document._log_attempt("generate", "error", str(exc))
                if isinstance(exc, (UserError, ValidationError)):
                    raise
                raise UserError(_("No fue posible generar el documento DIAN: %s") % exc) from exc
        return {"type": "ir.actions.client", "tag": "reload"}

    def action_validate_xml(self):
        for document in self:
            if not document.xml_file:
                document.action_generate()
                continue
            raw = base64.b64decode(document.xml_file)
            valid, errors = validate_xml(raw, document.is_adjustment)
            document.write({"state": "validated" if valid else "error", "xml_validation_errors": "\n".join(errors) if errors else False})
            if not valid:
                raise UserError(_("El XML no es válido:\n%s") % "\n".join(errors))
        return {"type": "ir.actions.client", "tag": "reload"}

    def _apply_response(self, response, operation):
        response = response if isinstance(response, dict) else {}
        dian = response.get("DianResponse") or []
        if isinstance(dian, dict):
            dian = [dian]
        first = dian[0] if dian else {}
        zip_key = response.get("ZipKey") or response.get("track_id") or first.get("ZipKey")
        xml_key = response.get("XmlDocumentKey") or first.get("XmlDocumentKey")
        status_code = response.get("StatusCode") or response.get("status_code") or first.get("StatusCode")
        errors = response.get("ErrorMessageList") or first.get("ErrorMessageList") or []
        message = response.get("StatusMessage") or response.get("status_message") or response.get("ErrorMessage") or response.get("error") or first.get("StatusDescription") or ("; ".join(errors) if errors else "")
        is_valid = response.get("IsValid") if "IsValid" in response else first.get("IsValid")
        values = {"response_log": json.dumps(response, ensure_ascii=False, indent=2, default=str), "zip_key": zip_key, "xml_document_key": xml_key, "status_code": status_code, "status_message": message or False, "error_message": False if is_valid else (message or False)}
        application_response = response.get("XmlBase64Bytes") or first.get("XmlBase64Bytes")
        if application_response:
            values.update({"application_response_file": application_response, "application_response_filename": f"{self.name}_ApplicationResponse.xml"})
        if is_valid is True:
            values["state"] = "accepted"
        elif is_valid is False or response.get("error"):
            values["state"] = "rejected"
        elif zip_key:
            values["state"] = "pending"
        elif not message:
            values.update({"state": "error", "error_message": _("La respuesta DIAN no contiene estado, ZipKey ni mensaje interpretable."), "error_category": "soap"})
        self.write(values)
        self._log_attempt(operation, "success" if values.get("state") != "rejected" else "rejected", message or "", response=response)

    def _soap_client(self):
        company = self.company_id
        material = company._co_dian_signing_material()
        if not material:
            raise UserError(_("Configura el certificado digital para autenticar la comunicación SOAP con la DIAN."))
        return DianSoapClient(
            company.co_dian_environment or "2",
            timeout=company.co_dian_request_timeout or 90,
            verify_ssl=True,
            certificate_data=material.get("certificate_data"),
            certificate_password=material.get("password") or "",
            pem_certificate=material.get("pem_certificate"),
            pem_key=material.get("pem_key"),
        )

    def action_send(self):
        for document in self:
            document.company_id.action_co_dian_validate_configuration()
            if document.state not in ("validated", "generated", "pending"):
                raise UserError(_("Solo se puede enviar un documento validado localmente."))
            if document.state == "pending":
                continue
            if document.zip_key or document.xml_document_key:
                raise UserError(_("Este documento ya tiene una referencia DIAN y no debe reenviarse. Consulta primero su estado."))
            if document.company_id.co_dian_environment == "1" and document.company_id.co_dian_require_habilitation and not document.company_id.co_dian_habilitation_ready:
                raise UserError(_("La compañía aún no cumple la habilitación mínima configurada: se requieren 4 nóminas y 4 notas de ajuste aceptadas."))
            document._prepare_send_approval()
            if document.preflight_state != "ok":
                document.action_prevalidate()
                document.invalidate_recordset(["preflight_state", "preflight_message"])
                if document.preflight_state != "ok":
                    raise UserError(_("La prevalidación no permite enviar el documento:\n%s") % (document.preflight_message or ""))
            if not document.xml_file or not document.zip_file:
                document.action_generate()
            try:
                client = document._soap_client()
                zip_bytes = base64.b64decode(document.zip_file)
                if document.company_id.co_dian_environment == "2":
                    if not document.company_id.co_dian_test_set_id:
                        raise UserError(_("Configura el Test Set ID para el ambiente de habilitación."))
                    response = client.send_test_set_async(document.zip_filename, zip_bytes, document.company_id.co_dian_test_set_id)
                else:
                    response = client.send_nomina_sync(zip_bytes, document.zip_filename)
                document.write({"sent_by": self.env.user.id, "sent_at": fields.Datetime.now(), "attempt_count": document.attempt_count + 1, "submission_environment": document.company_id.co_dian_environment, "request_log": json.dumps(response.get("request_xml") if isinstance(response, dict) else {}, ensure_ascii=False, default=str), "next_retry_at": False})
                document._apply_response(response, "send")
            except (DianSoapError, UserError) as exc:
                category = document._classify_error(exc)
                retry_count = document.retry_count + 1 if category in ("network", "soap") else document.retry_count
                can_retry = category in ("network", "soap") and document.company_id.co_dian_retry_enabled and retry_count <= document.company_id.co_dian_max_retries and not document.zip_key and not document.xml_document_key
                next_retry = fields.Datetime.now() + timedelta(minutes=document.company_id.co_dian_retry_delay_minutes) if can_retry else False
                document.write({"state": "error", "error_message": str(exc), "error_category": category, "attempt_count": document.attempt_count + 1, "retry_count": retry_count, "next_retry_at": next_retry})
                document._log_attempt("send", "error", str(exc))
                raise UserError(_("No fue posible transmitir a la DIAN: %s") % exc) from exc
        return {"type": "ir.actions.client", "tag": "reload"}

    def action_retry_send(self):
        for document in self:
            if document.state != "error" or document.error_category not in ("network", "soap"):
                raise UserError(_("Solo se pueden reintentar errores temporales de red o SOAP."))
            if document.zip_key or document.xml_document_key:
                raise UserError(_("El documento ya tiene referencia DIAN; consulta su estado en lugar de reenviarlo."))
            if document.retry_count >= document.company_id.co_dian_max_retries:
                raise UserError(_("Se alcanzó el máximo de reintentos configurado."))
            document.write({"state": "validated", "last_retry_at": fields.Datetime.now(), "next_retry_at": False})
            document.action_send()
        return {"type": "ir.actions.client", "tag": "reload"}

    def action_export_csv(self):
        if not self:
            raise UserError(_("Selecciona al menos un documento DIAN."))
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow([
            "Número", "Empleado", "Periodo", "Tipo", "Estado", "Ambiente", "CUNE", "ZipKey",
            "Código DIAN", "Mensaje", "Intentos", "Prevalidación",
        ])
        for document in self:
            writer.writerow([
                document.name or "", document.employee_id.display_name or "", document.period_id.display_name or "",
                "Nota de ajuste" if document.is_adjustment else "Nómina", document.state or "",
                document.submission_environment or document.company_id.co_dian_environment or "",
                document.cune or "", document.zip_key or "", document.status_code or "",
                document.error_message or document.status_message or "", document.attempt_count,
                document.preflight_state or "",
            ])
        attachment = self.env["ir.attachment"].sudo().create({
            "name": "nomina_dian_%s.csv" % fields.Date.context_today(self),
            "type": "binary",
            "datas": base64.b64encode(output.getvalue().encode("utf-8-sig")),
            "mimetype": "text/csv",
        })
        return {"type": "ir.actions.act_url", "url": "/web/content/%s?download=true" % attachment.id, "target": "self"}

    def action_check_status(self):
        for document in self:
            if not document.zip_key and not document.cune:
                raise UserError(_("El documento todavía no tiene CUNE ni ZipKey para consultar."))
            try:
                if document.company_id.co_dian_environment == "2" and document.zip_key:
                    operation = "get_status_zip"
                    response = document._soap_client().get_status_zip(document.zip_key)
                else:
                    operation = "get_status"
                    response = document._soap_client().get_status(document.cune)
                document.write({"last_checked_at": fields.Datetime.now(), "attempt_count": document.attempt_count + 1, "last_query_operation": operation})
                document._apply_response(response, "check_status")
            except (DianSoapError, UserError) as exc:
                document.write({"state": "error", "error_message": str(exc), "error_category": document._classify_error(exc), "attempt_count": document.attempt_count + 1})
                document._log_attempt("check_status", "error", str(exc))
                if document.env.context.get("co_dian_cron"):
                    continue
                raise UserError(_("No fue posible consultar el estado DIAN: %s") % exc) from exc
        return {"type": "ir.actions.client", "tag": "reload"}

    def action_fetch_application_response(self):
        for document in self:
            if not document.xml_document_key:
                raise UserError(_("El documento todavía no tiene XmlDocumentKey."))
            response = document._soap_client().get_xml_by_document_key(document.xml_document_key)
            encoded = response.get("XmlBase64Bytes") if isinstance(response, dict) else False
            if encoded:
                document.write({"application_response_file": encoded, "application_response_filename": f"{document.name}_ApplicationResponse.xml"})
            document._apply_response(response, "fetch_response")
        return {"type": "ir.actions.client", "tag": "reload"}

    def action_create_adjustment(self):
        self.ensure_one()
        if self.state != "accepted":
            raise UserError(_("Solo se puede crear una nota de ajuste a partir de un documento aceptado."))
        adjustment = self.copy({"name": False, "state": "draft", "is_adjustment": True, "tipo_nota": "1", "predecessor_id": self.id, "xml_file": False, "zip_file": False, "application_response_file": False, "cune": False, "cune_seed": False})
        return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": adjustment.id, "view_mode": "form", "target": "current"}

    @api.model
    def _cron_check_pending(self):
        documents = self.search([
            ("company_id.co_dian_auto_check_pending", "=", True),
            "|",
            "&", ("state", "=", "pending"), "|", ("zip_key", "!=", False), ("cune", "!=", False),
            "&", ("state", "=", "error"), ("error_category", "in", ["network", "soap"]),
            ("next_retry_at", "<=", fields.Datetime.now()),
        ], order="last_checked_at asc, id asc", limit=200)
        for document in documents:
            try:
                with self.env.cr.savepoint():
                    if document.state == "error":
                        document.with_context(co_dian_cron=True).action_retry_send()
                    else:
                        document.with_context(co_dian_cron=True).action_check_status()
            except Exception:
                # Un documento con un error inesperado no debe detener la consulta
                # de los demás pendientes.
                continue
        self.env["res.company"]._cron_create_dian_notifications()
        return True


class CoPayrollDianAttempt(models.Model):
    _name = "l10n.co.payroll.dian.attempt"
    _description = "Intento de comunicación nómina electrónica DIAN"
    _order = "create_date desc, id desc"
    _check_company_auto = True

    document_id = fields.Many2one("l10n.co.payroll.dian.document", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="document_id.company_id", store=True, readonly=True)
    operation = fields.Selection([("generate", "Generación"), ("approve", "Aprobación"), ("send", "Envío"), ("check_status", "Consulta"), ("fetch_response", "Respuesta")], required=True)
    status = fields.Selection([("success", "Exitoso"), ("rejected", "Rechazado"), ("error", "Error")], required=True)
    message = fields.Text()
    technical_detail = fields.Text()
    response = fields.Text()
    cune = fields.Char()
    zip_key = fields.Char()

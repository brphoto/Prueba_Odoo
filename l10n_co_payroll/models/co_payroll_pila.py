import base64
import csv
import hashlib
import io

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class CoPayrollPilaConfig(models.Model):
    _name = "l10n.co.payroll.pila.config"
    _description = "Configuración de exportación PILA"
    _order = "company_id, name"
    _check_company_auto = True

    name = fields.Char(string="Nombre", required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    operator = fields.Selection([("generic", "Archivo configurable"), ("soporte", "Operador / soporte"), ("other", "Otro")], string="Operador", required=True, default="generic")
    file_format = fields.Selection([("csv", "CSV delimitado"), ("fixed", "Ancho fijo")], string="Formato", required=True, default="csv")
    delimiter = fields.Char(string="Separador", required=True, default=";")
    encoding = fields.Selection([("utf-8-sig", "UTF-8 con BOM"), ("cp1252", "ANSI / Windows-1252")], string="Codificación", required=True, default="cp1252")
    include_header = fields.Boolean(string="Incluir encabezado", default=False)
    filename_prefix = fields.Char(string="Prefijo de archivo", default="PILA")
    active = fields.Boolean(default=True)
    legal_reference = fields.Text(string="Referencia legal / técnica")

    _company_name_unique = models.Constraint("unique(company_id, name)", "Ya existe una configuración PILA con este nombre.")


class CoPayrollPilaFile(models.Model):
    _name = "l10n.co.payroll.pila.file"
    _description = "Archivo PILA de nómina"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "generated_at desc, id desc"
    _check_company_auto = True

    name = fields.Char(string="Referencia", required=True, copy=False, default=lambda self: _("Archivo PILA"), tracking=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    period_id = fields.Many2one("l10n.co.payroll.period", required=True, ondelete="restrict", index=True, tracking=True)
    config_id = fields.Many2one("l10n.co.payroll.pila.config", string="Configuración", required=True, domain="[('company_id', '=', company_id), ('active', '=', True)]")
    state = fields.Selection([("draft", "Borrador"), ("validated", "Validado"), ("generated", "Generado"), ("exported", "Exportado"), ("cancelled", "Cancelado")], default="draft", required=True, tracking=True)
    attachment_id = fields.Many2one("ir.attachment", string="Archivo", readonly=True, copy=False)
    datas = fields.Binary(related="attachment_id.datas", readonly=True)
    filename = fields.Char(related="attachment_id.name", readonly=True)
    generated_by = fields.Many2one("res.users", readonly=True, copy=False)
    generated_at = fields.Datetime(readonly=True, copy=False)
    record_count = fields.Integer(readonly=True, copy=False)
    checksum = fields.Char(readonly=True, copy=False)
    validation_message = fields.Text(readonly=True, copy=False)

    @api.constrains("period_id", "config_id")
    def _check_pila_company(self):
        for record in self:
            if record.period_id.company_id != record.company_id or record.config_id.company_id != record.company_id:
                raise ValidationError(_("El periodo y la configuración PILA deben pertenecer a la misma compañía."))

    def _validate_lines(self):
        self.ensure_one()
        errors = []
        for line in self.period_id.line_ids:
            if not line.employee_id.identification_id:
                errors.append(_("%s: falta identificación.") % line.employee_id.name)
            if not line.social_profile_id:
                errors.append(_("%s: falta perfil PILA vigente.") % line.employee_id.name)
            if not line.pila_type:
                errors.append(_("%s: falta tipo de cotizante.") % line.employee_id.name)
            if line.pila_type and line.pila_type not in ("01", "02", "03", "04", "12", "19", "23", "40", "51", "52"):
                errors.append(_("%s: el tipo de cotizante PILA no está en el catálogo configurado.") % line.employee_id.name)
            if line.social_profile_id and not line.eps_code:
                errors.append(_("%s: falta código EPS.") % line.employee_id.name)
            if line.social_profile_id and not line.pension_code:
                errors.append(_("%s: falta código AFP.") % line.employee_id.name)
            if line.social_profile_id and not line.arl_code:
                errors.append(_("%s: falta código ARL.") % line.employee_id.name)
            if line.social_profile_id and not line.ccf_code:
                errors.append(_("%s: falta código de caja de compensación.") % line.employee_id.name)
            if line.worked_days < 0 or line.worked_days > 31:
                errors.append(_("%s: los días PILA deben estar entre 0 y 31.") % line.employee_id.name)
            minimum_ibc = self.period_id.parameter_id.minimum_ibc if self.period_id.parameter_id and "minimum_ibc" in self.period_id.parameter_id._fields else 0.0
            if minimum_ibc and line.ibc_base < minimum_ibc:
                errors.append(_("%s: el IBC está por debajo del mínimo configurado.") % line.employee_id.name)
        return errors

    def action_validate(self):
        for record in self:
            if record.period_id.state not in ("ready", "closed"):
                raise UserError(_("El periodo debe estar preparado o cerrado para validar PILA."))
            errors = record._validate_lines()
            record.write({"state": "draft" if errors else "validated", "validation_message": "\n".join(errors) or _("Validación exitosa.")})
        return True

    def _build_content(self):
        self.ensure_one()
        headers = ["tipo_documento", "numero_documento", "empleado", "tipo_cotizante", "subtipo", "dias", "ibc", "novedades", "eps", "afp", "arl", "caja", "clase_riesgo", "salud_empleado", "salud_empleador", "pension_empleado", "pension_empleador", "solidaridad", "arl_empleador", "caja_empleador"]
        rows = []
        for line in self.period_id.line_ids:
            rows.append([line.social_profile_id.identification_type if line.social_profile_id else "CC", line.employee_id.identification_id or "", line.employee_id.name, line.pila_type or "", line.pila_subtype or "", round(line.worked_days or 0), round(line.ibc_base or 0), line.pila_novelty_codes or "", line.eps_code or "", line.pension_code or "", line.arl_code or "", line.ccf_code or "", line.risk_class or "", round(line.health_employee or 0), round(line.health_employer or 0), round(line.pension_employee or 0), round(line.pension_employer or 0), round(line.solidarity_employee or 0), round(line.arl_employer or 0), round(line.ccf_employer or 0)])
        if self.config_id.file_format == "fixed":
            widths = [4, 20, 60, 4, 4, 3, 15, 20, 12, 12, 12, 12, 4, 15, 15, 15, 15, 15, 15, 15]
            fixed_rows = [headers] if self.config_id.include_header else []
            fixed_rows += rows
            return "".join("".join(str(value or "")[:width].ljust(width) for value, width in zip(row, widths)) + "\r\n" for row in fixed_rows)
        output = io.StringIO(newline="")
        writer = csv.writer(output, delimiter=self.config_id.delimiter or ";", lineterminator="\r\n")
        if self.config_id.include_header:
            writer.writerow(headers)
        writer.writerows(rows)
        return output.getvalue()

    def action_generate(self):
        for record in self:
            record.action_validate()
            if record.state != "validated":
                raise UserError(_("Corrige las validaciones PILA antes de generar el archivo."))
            content = record._build_content()
            encoded = content.encode(record.config_id.encoding or "cp1252", errors="replace")
            filename = "%s_%s.%s" % (record.config_id.filename_prefix or "PILA", record.period_id.name.replace("/", "-"), "csv" if record.config_id.file_format == "csv" else "txt")
            attachment = self.env["ir.attachment"].create({"name": filename, "type": "binary", "datas": base64.b64encode(encoded), "res_model": record._name, "res_id": record.id, "mimetype": "text/csv"})
            record.write({"attachment_id": attachment.id, "state": "generated", "generated_by": self.env.user.id, "generated_at": fields.Datetime.now(), "record_count": len(record.period_id.line_ids), "checksum": hashlib.sha256(encoded).hexdigest()})
            self.env["l10n.co.payroll.audit"].sudo().create({"company_id": record.company_id.id, "period_id": record.period_id.id, "res_model": record._name, "res_id": record.id, "action": "pila", "description": _("Archivo PILA configurable generado: %s.") % filename})
        return True

    def action_mark_exported(self):
        self.filtered(lambda record: record.state == "generated").write({"state": "exported"})
        return True

    def action_download(self):
        self.ensure_one()
        if not self.attachment_id:
            raise UserError(_("Genera el archivo antes de descargarlo."))
        self.action_mark_exported()
        return {"type": "ir.actions.act_url", "url": "/web/content/%s?download=true" % self.attachment_id.id, "target": "self"}

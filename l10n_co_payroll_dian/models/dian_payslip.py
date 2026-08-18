from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CoPayrollDianPayslip(models.Model):
    _inherit = "hr.payslip"

    co_dian_document_ids = fields.Many2many(
        "l10n.co.payroll.dian.document",
        string="Detalle de documentos DIAN",
        compute="_compute_co_dian_status",
    )
    co_dian_document_id = fields.Many2one(
        "l10n.co.payroll.dian.document",
        string="Documento DIAN principal",
        compute="_compute_co_dian_status",
    )
    co_dian_document_count = fields.Integer(
        string="Cantidad de documentos DIAN",
        compute="_compute_co_dian_status",
    )
    co_dian_state = fields.Selection([
        ("none", "Sin documento"),
        ("draft", "Borrador"),
        ("generated", "Generado / validado"),
        ("pending", "Pendiente de respuesta DIAN"),
        ("accepted", "Aceptado por la DIAN"),
        ("rejected", "Rechazado"),
        ("error", "Error"),
    ], string="Estado DIAN", compute="_compute_co_dian_status")
    co_dian_attention_level = fields.Selection(
        string="Nivel de atención DIAN",
        selection=[
            ("success", "Correcto"), ("info", "Información"),
            ("warning", "Atención"), ("danger", "Crítico"),
        ],
        compute="_compute_co_dian_status",
    )
    co_dian_attention_message = fields.Char(
        string="Seguimiento DIAN",
        compute="_compute_co_dian_status",
    )
    co_dian_number = fields.Char(
        string="Número DIAN",
        compute="_compute_co_dian_status",
    )
    co_dian_cune = fields.Char(
        string="CUNE",
        compute="_compute_co_dian_status",
    )
    co_dian_status_code = fields.Char(
        string="Código DIAN",
        compute="_compute_co_dian_status",
    )
    co_dian_status_message = fields.Text(
        string="Respuesta DIAN",
        compute="_compute_co_dian_status",
    )
    co_dian_environment = fields.Selection(
        string="Ambiente DIAN",
        selection=[("1", "Producción"), ("2", "Habilitación")],
        compute="_compute_co_dian_status",
    )
    co_dian_generated_at = fields.Datetime(
        string="Generado el",
        compute="_compute_co_dian_status",
    )
    co_dian_sent_at = fields.Datetime(
        string="Enviado el",
        compute="_compute_co_dian_status",
    )
    co_dian_last_checked_at = fields.Datetime(
        string="Última consulta DIAN",
        compute="_compute_co_dian_status",
    )
    co_dian_zip_key = fields.Char(
        string="ZipKey / Track ID",
        compute="_compute_co_dian_status",
    )
    co_dian_xml_document_key = fields.Char(
        string="XmlDocumentKey",
        compute="_compute_co_dian_status",
    )
    co_dian_attempt_ids = fields.Many2many(
        "l10n.co.payroll.dian.attempt",
        string="Detalle de intentos DIAN",
        compute="_compute_co_dian_status",
    )
    co_dian_attempt_count = fields.Integer(
        string="Cantidad de intentos DIAN",
        compute="_compute_co_dian_status",
    )
    co_dian_last_attempt_at = fields.Datetime(
        string="Último intento",
        compute="_compute_co_dian_status",
    )
    co_dian_last_operation = fields.Selection(
        [
            ("generate", "Generación"), ("approve", "Aprobación"),
            ("send", "Envío"), ("check_status", "Consulta"),
            ("fetch_response", "Respuesta"),
        ],
        string="Última operación",
        compute="_compute_co_dian_status",
    )
    co_dian_last_attempt_status = fields.Selection(
        [("success", "Exitoso"), ("rejected", "Rechazado"), ("error", "Error")],
        string="Resultado del último intento",
        compute="_compute_co_dian_status",
    )
    co_dian_last_attempt_message = fields.Text(
        string="Mensaje del último intento",
        compute="_compute_co_dian_status",
    )
    co_dian_error_category = fields.Selection(
        [
            ("data", "Datos"), ("xml", "XML/XSD"),
            ("signature", "Firma"), ("certificate", "Certificado"),
            ("soap", "SOAP/DIAN"), ("network", "Red"),
        ],
        string="Categoría del error",
        compute="_compute_co_dian_status",
    )

    def _co_dian_post_validation_message(self, message):
        """Leave a short, auditable result on the native payslip chatter."""
        for slip in self:
            if hasattr(slip, "message_post"):
                slip.message_post(
                    body=message,
                    message_type="notification",
                    subtype_xmlid="mail.mt_note",
                )

    def _co_dian_process_after_validation(self):
        """Generate the signed local XML after native Odoo confirmation.

        The payroll confirmation must remain independent from DIAN connectivity:
        a network, certificate or data issue is recorded on the DIAN document and
        in the payslip chatter without undoing Odoo's native payroll validation.
        """
        for slip in self:
            company = slip.company_id
            if not company.co_dian_payroll_enabled or not company.co_dian_auto_generate_on_validate:
                continue
            try:
                documents = slip._co_dian_get_or_create_documents()
            except UserError as exc:
                slip._co_dian_post_validation_message(
                    _("Nómina confirmada. El XML DIAN no se generó todavía: %s") % exc
                )
                continue
            document = documents.filtered(lambda doc: not doc.is_adjustment)[:1]
            if not document:
                continue
            try:
                if document.state in ("draft", "error"):
                    document.action_generate()
                elif document.state not in ("validated", "generated"):
                    slip._co_dian_post_validation_message(
                        _("Nómina confirmada. El documento DIAN %s conserva el estado «%s» y no se reemplazará automáticamente.")
                        % (document.name, document.state)
                    )
                    continue
                slip._co_dian_post_validation_message(
                    _("Nómina confirmada. XML DIAN firmado y validado localmente: %s.") % document.name
                )
                if company.co_dian_auto_send_on_validate and document.state in ("validated", "generated"):
                    if company.co_dian_approval_mode == "none":
                        document.action_send()
                        slip._co_dian_post_validation_message(
                            _("Documento %s enviado a la DIAN; queda pendiente de respuesta.") % document.name
                        )
                    else:
                        slip._co_dian_post_validation_message(
                            _("Documento %s listo para envío. Debe completar la aprobación DIAN configurada.") % document.name
                        )
            except Exception as exc:
                # action_generate/action_send already store the detailed error on
                # the DIAN document. Keep the native payroll confirmation intact.
                slip._co_dian_post_validation_message(
                    _("Nómina confirmada, pero el proceso DIAN requiere atención: %s") % exc
                )

    def action_payslip_done(self):
        result = super().action_payslip_done()
        self._co_dian_process_after_validation()
        return result

    @api.depends("employee_id", "date_from", "date_to")
    def _compute_co_dian_status(self):
        period_line_model = self.env["l10n.co.payroll.period.line"]
        document_model = self.env["l10n.co.payroll.dian.document"]
        for slip in self:
            lines = period_line_model.search([
                ("source_payslip_ids", "in", slip.id),
            ])
            documents = document_model.search([
                ("period_line_id", "in", lines.ids),
                ("is_adjustment", "=", False),
            ], order="id desc") if lines else document_model
            slip.co_dian_document_ids = documents
            document = documents[:1]
            slip.co_dian_document_id = document.id if document else False
            slip.co_dian_document_count = len(documents)
            slip.co_dian_attention_level = document.attention_level if document else False
            slip.co_dian_attention_message = document.attention_message if document else False
            slip.co_dian_number = document.name if document else False
            slip.co_dian_cune = document.cune if document else False
            slip.co_dian_status_code = document.status_code if document else False
            slip.co_dian_status_message = document.status_message if document else False
            slip.co_dian_environment = (
                document.submission_environment
                if document and document.submission_environment
                else slip.company_id.co_dian_environment
            )
            slip.co_dian_generated_at = document.generated_at if document else False
            slip.co_dian_sent_at = document.sent_at if document else False
            slip.co_dian_last_checked_at = document.last_checked_at if document else False
            slip.co_dian_zip_key = document.zip_key if document else False
            slip.co_dian_xml_document_key = document.xml_document_key if document else False
            attempts = document.attempt_ids if document else self.env["l10n.co.payroll.dian.attempt"]
            last_attempt = attempts[:1]
            slip.co_dian_attempt_ids = attempts
            slip.co_dian_attempt_count = len(attempts)
            slip.co_dian_last_attempt_at = last_attempt.create_date if last_attempt else False
            slip.co_dian_last_operation = last_attempt.operation if last_attempt else False
            slip.co_dian_last_attempt_status = last_attempt.status if last_attempt else False
            slip.co_dian_last_attempt_message = last_attempt.message if last_attempt else False
            slip.co_dian_error_category = document.error_category if document else False
            if not documents:
                slip.co_dian_state = "none"
            elif documents.filtered(lambda doc: doc.state == "error"):
                slip.co_dian_state = "error"
            elif documents.filtered(lambda doc: doc.state == "rejected"):
                slip.co_dian_state = "rejected"
            elif documents.filtered(lambda doc: doc.state == "pending"):
                slip.co_dian_state = "pending"
            elif documents.filtered(lambda doc: doc.state in ("validated", "generated")):
                slip.co_dian_state = "generated"
            elif all(doc.state == "accepted" for doc in documents):
                slip.co_dian_state = "accepted"
            else:
                slip.co_dian_state = "draft"

    def _co_dian_find_documents(self):
        self.ensure_one()
        period_line_model = self.env["l10n.co.payroll.period.line"]
        document_model = self.env["l10n.co.payroll.dian.document"]
        lines = period_line_model.search([("source_payslip_ids", "in", self.id)])
        if not lines:
            raise UserError(_("Este recibo aún no está asociado a una línea de período de Nómina Colombia."))
        return document_model.search([
            ("period_line_id", "in", lines.ids),
            ("is_adjustment", "=", False),
        ], order="id desc")

    def _co_dian_get_or_create_documents(self):
        self.ensure_one()
        documents = self._co_dian_find_documents()
        if not documents:
            period_line_model = self.env["l10n.co.payroll.period.line"]
            document_model = self.env["l10n.co.payroll.dian.document"]
            lines = period_line_model.search([("source_payslip_ids", "in", self.id)])
            documents = document_model.create({
                "period_id": lines[0].period_id.id,
                "period_line_id": lines[0].id,
                "company_id": lines[0].company_id.id,
            })
        return documents

    def action_co_dian_open_document(self):
        self.ensure_one()
        documents = self._co_dian_find_documents()
        if not documents:
            raise UserError(_("Este recibo todavía no tiene un documento DIAN generado."))
        if len(documents) == 1:
            return {
                "type": "ir.actions.act_window",
                "name": _("Documento DIAN"),
                "res_model": "l10n.co.payroll.dian.document",
                "view_mode": "form",
                "res_id": documents.id,
            }
        return {
            "type": "ir.actions.act_window",
            "name": _("Documentos DIAN del recibo"),
            "res_model": "l10n.co.payroll.dian.document",
            "view_mode": "list,form",
            "domain": [("id", "in", documents.ids)],
        }

    def action_co_dian_generate_document(self):
        for slip in self:
            documents = slip._co_dian_get_or_create_documents().filtered(lambda doc: not doc.is_adjustment)
            documents.filtered(lambda doc: doc.state in ("draft", "error")).action_generate()
        return {"type": "ir.actions.client", "tag": "soft_reload"}

    def action_co_dian_prevalidate_document(self):
        for slip in self:
            slip._co_dian_get_or_create_documents().filtered(lambda doc: not doc.is_adjustment).action_prevalidate()
        return {"type": "ir.actions.client", "tag": "soft_reload"}

    def action_co_dian_send_document(self):
        for slip in self:
            documents = slip._co_dian_find_documents().filtered(
                lambda doc: not doc.is_adjustment and doc.state in ("validated", "generated")
            )
            if not documents:
                raise UserError(_("Este recibo no tiene un documento DIAN listo para enviar."))
            documents.action_send()
        return {"type": "ir.actions.client", "tag": "soft_reload"}

    def action_co_dian_check_document(self):
        for slip in self:
            documents = slip._co_dian_find_documents().filtered(lambda doc: (
                not doc.is_adjustment and doc.state == "pending" and (doc.zip_key or doc.cune)
            ))
            if not documents:
                raise UserError(_("Este recibo no tiene un envío DIAN pendiente de consulta."))
            documents.action_check_status()
        return {"type": "ir.actions.client", "tag": "soft_reload"}

import base64

from odoo import fields, http
from odoo.http import content_disposition, request


class CoPayrollPortalController(http.Controller):
    def _employee(self):
        return request.env["hr.employee"].sudo().search([("user_id", "=", request.env.user.id), ("active", "=", True)], limit=1)

    @http.route("/my/payroll", type="http", auth="user", website=True)
    def payroll_home(self, **kwargs):
        employee = self._employee()
        payslips = request.env["hr.payslip"].sudo().search([("employee_id", "=", employee.id), ("state", "in", ["validated", "paid"])], order="date_to desc, id desc", limit=60) if employee else request.env["hr.payslip"]
        requests = request.env["l10n.co.payroll.portal.request"].sudo().search([("employee_id", "=", employee.id)], order="create_date desc") if employee else request.env["l10n.co.payroll.portal.request"]
        documents = request.env["l10n.co.payroll.employee.document"].sudo().search([("employee_id", "=", employee.id), ("state", "=", "published"), ("portal_visible", "=", True)], order="document_date desc, id desc") if employee and "l10n.co.payroll.employee.document" in request.env.registry.models else request.env["hr.payslip"].browse()
        return request.render("l10n_co_payroll_portal.portal_payroll_dashboard", {"employee": employee, "payslips": payslips, "requests": requests, "documents": documents})

    @http.route("/my/payroll/profile", type="http", auth="user", website=True)
    def payroll_profile(self, **kwargs):
        return request.render("l10n_co_payroll_portal.portal_payroll_profile", {"employee": self._employee()})

    @http.route("/my/payroll/profile/update", type="http", auth="user", website=True, methods=["POST"], csrf=True)
    def payroll_profile_update(self, **post):
        employee = self._employee()
        if employee:
            details = [
                "Correo: %s" % (post.get("work_email") or "Sin cambio"),
                "Teléfono: %s" % (post.get("work_phone") or "Sin cambio"),
                "Celular: %s" % (post.get("mobile_phone") or "Sin cambio"),
                "Dirección: %s" % (post.get("address") or "Sin cambio"),
            ]
            request.env["l10n.co.payroll.portal.request"].sudo().create({"company_id": employee.company_id.id, "employee_id": employee.id, "request_type": "data_change", "description": "Solicitud de actualización de información personal.\n" + "\n".join(details), "state": "submitted"})
        return request.redirect("/my/payroll/requests")

    @http.route("/my/payroll/advance", type="http", auth="user", website=True)
    def payroll_advance(self, **kwargs):
        return request.render("l10n_co_payroll_portal.portal_payroll_financial_request", {"employee": self._employee(), "request_type": "advance", "title": "Solicitar anticipo", "subtitle": "Envía una solicitud de anticipo de nómina para revisión de gestión humana.", "button": "Enviar solicitud de anticipo"})

    @http.route("/my/payroll/loan", type="http", auth="user", website=True)
    def payroll_loan(self, **kwargs):
        return request.render("l10n_co_payroll_portal.portal_payroll_financial_request", {"employee": self._employee(), "request_type": "loan", "title": "Solicitar préstamo", "subtitle": "Registra el valor y el plazo deseado. La aprobación queda sujeta a las políticas de la empresa.", "button": "Enviar solicitud de préstamo"})

    @http.route("/my/payroll/payslips", type="http", auth="user", website=True)
    def payroll_payslips(self, **kwargs):
        employee = self._employee()
        payslips = request.env["hr.payslip"].sudo().search([("employee_id", "=", employee.id), ("state", "in", ["validated", "paid", "done"])], order="date_to desc, id desc", limit=60) if employee else request.env["hr.payslip"]
        if employee:
            request.env["l10n.co.payroll.portal.access.log"].sudo().create({"company_id": employee.company_id.id, "employee_id": employee.id, "action": "view", "ip_address": request.httprequest.remote_addr})
        return request.render("l10n_co_payroll_portal.portal_payroll_payslips", {"employee": employee, "payslips": payslips})

    @http.route("/my/payroll/payslip/<int:payslip_id>", type="http", auth="user", website=True)
    def payroll_payslip(self, payslip_id, **kwargs):
        employee = self._employee()
        payslip = request.env["hr.payslip"].sudo().search([("id", "=", payslip_id), ("employee_id", "=", employee.id), ("state", "in", ["validated", "paid", "done"])], limit=1)
        if not payslip:
            return request.not_found()
        request.env["l10n.co.payroll.portal.access.log"].sudo().create({"company_id": employee.company_id.id, "employee_id": employee.id, "payslip_id": payslip.id, "action": "view", "ip_address": request.httprequest.remote_addr})
        return request.render("l10n_co_payroll_portal.portal_payroll_payslip", {"employee": employee, "payslip": payslip})

    @http.route("/my/payroll/payslip/<int:payslip_id>/pdf", type="http", auth="user", website=True)
    def payroll_payslip_pdf(self, payslip_id, **kwargs):
        employee = self._employee()
        payslip = request.env["hr.payslip"].sudo().search([("id", "=", payslip_id), ("employee_id", "=", employee.id), ("state", "in", ["validated", "paid", "done"])], limit=1)
        if not payslip:
            return request.not_found()
        request.env["l10n.co.payroll.portal.access.log"].sudo().create({"company_id": employee.company_id.id, "employee_id": employee.id, "payslip_id": payslip.id, "action": "download", "ip_address": request.httprequest.remote_addr})
        pdf, _ = request.env["ir.actions.report"].sudo()._render_qweb_pdf("l10n_co_payroll_portal.action_report_portal_payslip", payslip.ids)
        return request.make_response(pdf, headers=[("Content-Type", "application/pdf"), ("Content-Disposition", content_disposition("Desprendible-%s.pdf" % payslip.name))])

    @http.route("/my/payroll/requests", type="http", auth="user", website=True)
    def payroll_requests(self, **kwargs):
        employee = self._employee()
        requests = request.env["l10n.co.payroll.portal.request"].sudo().search([("employee_id", "=", employee.id)], order="create_date desc") if employee else request.env["l10n.co.payroll.portal.request"]
        return request.render("l10n_co_payroll_portal.portal_payroll_requests", {"employee": employee, "requests": requests})

    @http.route("/my/payroll/documents", type="http", auth="user", website=True)
    def payroll_documents(self, **kwargs):
        employee = self._employee()
        documents = request.env["hr.payslip"].browse()
        if "l10n.co.payroll.employee.document" in request.env.registry.models:
            documents = request.env["l10n.co.payroll.employee.document"].sudo().search([
                ("employee_id", "=", employee.id if employee else 0),
                ("state", "=", "published"),
                ("portal_visible", "=", True),
                "|", ("expiry_date", "=", False), ("expiry_date", ">=", fields.Date.context_today(request.env.user)),
            ], order="document_date desc, id desc")
        return request.render("l10n_co_payroll_portal.portal_payroll_documents", {"employee": employee, "documents": documents})

    @http.route("/my/payroll/document/<int:document_id>/download", type="http", auth="user", website=True)
    def payroll_document_download(self, document_id, **kwargs):
        employee = self._employee()
        if "l10n.co.payroll.employee.document" not in request.env.registry.models:
            return request.not_found()
        document = request.env["l10n.co.payroll.employee.document"].sudo().search([
            ("id", "=", document_id), ("employee_id", "=", employee.id if employee else 0),
            ("state", "=", "published"), ("portal_visible", "=", True),
            "|", ("expiry_date", "=", False), ("expiry_date", ">=", fields.Date.context_today(request.env.user)),
        ], limit=1)
        if not document or not document.attachment_id:
            return request.not_found()
        request.env["l10n.co.payroll.portal.access.log"].sudo().create({"company_id": employee.company_id.id, "employee_id": employee.id, "action": "download", "ip_address": request.httprequest.remote_addr})
        attachment = document.attachment_id
        payload = base64.b64decode(attachment.datas or b"")
        return request.make_response(payload, headers=[("Content-Type", attachment.mimetype or "application/octet-stream"), ("Content-Disposition", content_disposition(document.filename or document.name))])

    @http.route("/my/payroll/request/create", type="http", auth="user", website=True, methods=["POST"], csrf=True)
    def payroll_request_create(self, **post):
        employee = self._employee()
        if employee and post.get("description"):
            amount = float(post.get("requested_amount") or 0)
            installments = int(post.get("installment_count") or 0)
            request.env["l10n.co.payroll.portal.request"].sudo().create({"company_id": employee.company_id.id, "employee_id": employee.id, "request_type": post.get("request_type", "other"), "date_from": post.get("date_from") or False, "date_to": post.get("date_to") or False, "description": post.get("description"), "bank_account_number": post.get("bank_account_number") or False, "bank_name": post.get("bank_name") or False, "requested_amount": amount, "installment_count": installments, "state": "submitted"})
        return request.redirect("/my/payroll/requests")

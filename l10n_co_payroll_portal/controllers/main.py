import base64

from odoo import fields, http
from odoo.http import content_disposition, request


class CoPayrollPortalController(http.Controller):
    def _employee(self):
        return request.env["hr.employee"].sudo().search([("user_id", "=", request.env.user.id), ("active", "=", True)], limit=1)

    @http.route("/my/payroll", type="http", auth="user", website=True)
    def payroll_home(self, **kwargs):
        return request.redirect("/my/payroll/payslips")

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
        pdf, _ = request.env["ir.actions.report"].sudo()._render_qweb_pdf("hr_payroll.report_payslip_lang", payslip.ids)
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
            request.env["l10n.co.payroll.portal.request"].sudo().create({"company_id": employee.company_id.id, "employee_id": employee.id, "request_type": post.get("request_type", "other"), "date_from": post.get("date_from") or False, "date_to": post.get("date_to") or False, "description": post.get("description"), "bank_account_number": post.get("bank_account_number") or False, "bank_name": post.get("bank_name") or False})
        return request.redirect("/my/payroll/requests")

import logging

from odoo import http
from odoo.http import request
from odoo.tools import email_split
from datetime import datetime, time, timedelta
import base64
from math import ceil

_logger = logging.getLogger(__name__)


class PartnerForm(http.Controller):
    def _get_employee(self):
        """Empleado del portal asociado al usuario logueado (por work_email == login)."""
        return request.env['hr.employee'].sudo().search(
            [('work_email', '=', request.env.user.login)], limit=1)

    def _get_leave_types(self, employee):
        """Tipos de ausencia disponibles para el empleado. Se filtran por
        contract_type cuando esa configuración existe; si ningún tipo de
        ausencia tiene el campo contract_type configurado (dato pendiente de
        RRHH), se listan todos los tipos activos y compatibles en vez de
        dejar el desplegable vacío y el formulario inutilizable.

        El filtro adicional evita ofrecer tipos que:
        - requieren una asignación de días previa (el empleado nunca la
          tendría, y el envío fallaría con un error confuso), o
        - tienen un país distinto al de la compañía (la regla nativa de
          Odoo "Time Off multi company rule" los oculta igual al crear la
          ausencia, así que mostrarlos en el formulario también sería
          engañoso: el envío fallaría con "Record does not exist").
        """
        Leave = request.env['hr.leave.type'].sudo()
        leave = Leave.search([('contract_type.code', '=', employee.contract_type)])
        if not leave:
            company_country_id = employee.company_id.country_id.id
            leave = Leave.search([
                ('active', '=', True),
                ('requires_allocation', '=', False),
                ('country_id', 'in', [False, company_country_id]),
            ])
        return leave

    def _get_user_email(self, user):
        email = user.partner_id.email or user.email or user.login
        return email if email and email_split(email) else False

    def _send_mail(self, mail_values):
        mail = request.env['mail.mail'].sudo().create(mail_values)
        mail.send(raise_exception=True)
        return mail

    def _get_vacation_summary(self, empleado):
        """Resumen de saldos (self care day + vacaciones) del empleado, para el
        dashboard y el historial de ausencias."""
        year = datetime.now().year
        primer_dia = datetime(year, 1, 1)
        ultimo_dia = datetime(year, 12, 31)

        leave_selfcare = sum(request.env['hr.leave'].sudo().search([
            ('employee_id', '=', empleado.id),
            ('state', '=', 'validate'),
            ('holiday_status_id', '=', request.env.ref('hr_leave_type.leave_type_self').id),
            ('date_from', '>=', primer_dia),
            ('date_from', '<=', ultimo_dia)],
            order='request_date_from desc').mapped('number_of_days'))

        if empleado.contract_type == '2':
            leave_vac = sum(request.env['hr.leave'].sudo().search([
                ('employee_id', '=', empleado.id),
                ('state', '=', 'validate'),
                ('holiday_status_id', '=', request.env.ref('hr_leave_type.leave_type_freelance_unpaid').id)],
                order='request_date_from desc').mapped('number_of_days'))
        else:
            leave_vac = sum(request.env['hr.leave'].sudo().search([
                ('employee_id', '=', empleado.id),
                ('state', '=', 'validate'),
                ('holiday_status_id', '=', request.env.ref('hr_leave_type.leave_type_vac').id)],
                order='request_date_from desc').mapped('number_of_days'))

        vacs_days = request.env['hr.leave'].get_vacations(empleado)

        installed = request.env['ir.module.module'].sudo().search([
            ('name', '=', 'hr_initial_values_19e'),
            ('state', '=', 'installed')], limit=1)
        days = 0
        if installed:
            days = sum(request.env['hr.initial.value'].sudo().search([
                ('employee_id', '=', empleado.id)]).mapped('vacations_days'))

        if empleado.contract_type == '2':
            combinado = [{
                'name': 'SELF CARE DAY',
                'value': round(int(leave_selfcare), 2),
                'res': round(2 - int(leave_selfcare), 2),
                'total': round(2, 2),
            }, {
                'name': ' SIN PRESTACION DE SERVICIOS',
                'value': round(int(leave_vac) + int(days), 2),
                'res': round(int(vacs_days) - int(leave_vac) - int(days), 2),
                'total': round(vacs_days, 2),
            }]
        else:
            combinado = [{
                'name': 'SELF CARE DAY',
                'value': round(leave_selfcare, 2),
                'res': round(2 - leave_selfcare, 2),
                'total': round(2, 2),
            }, {
                'name': 'VACACIONES',
                'value': round(int(leave_vac) + int(days), 2),
                'res': round(int(vacs_days) - int(leave_vac) - int(days), 2),
                'total': round(vacs_days, 2),
            }]
        return combinado

    @http.route(['/portal/inicio'], type='http', auth='user', website=True)
    def portal_home(self, **post):
        empleado = self._get_employee()
        combinado = self._get_vacation_summary(empleado) if empleado else []

        vac_restantes = combinado[1]['res'] if len(combinado) > 1 else 0
        vac_total = combinado[1]['total'] if len(combinado) > 1 else 0
        vac_pct = int(round((vac_restantes / vac_total) * 100)) if vac_total else 0
        selfcare_restantes = combinado[0]['res'] if combinado else 0
        # Aviso simple para que el empleado no acumule demasiados días sin
        # planificarlos (45 días ≈ 1.5 períodos anuales completos); no es un
        # vencimiento legal automático, solo una señal para organizarse.
        vac_acumulacion_alta = vac_restantes >= 45

        pendientes_count = request.env['hr.leave'].sudo().search_count([
            ('employee_id', '=', empleado.id),
            ('state', 'in', ('confirm', 'validate1')),
        ]) if empleado else 0

        ultimas_ausencias = request.env['hr.leave'].sudo().search([
            ('employee_id', '=', empleado.id)],
            order='create_date desc', limit=5) if empleado else []

        if empleado and empleado.contract_type != '2':
            payslip_domain = [('employee_id', '=', empleado.id), ('state', 'in', ('validated', 'paid'))]
            payslip_count = request.env['hr.payslip'].sudo().search_count(payslip_domain)
            ultimo_payslip = request.env['hr.payslip'].sudo().search(payslip_domain, order='date_from desc', limit=1)
        else:
            payslip_count = 0
            ultimo_payslip = False

        return request.render("website_ausencias_19e.portal_home", {
            'employee': empleado,
            'vac_restantes': vac_restantes,
            'vac_pct': vac_pct,
            'vac_acumulacion_alta': vac_acumulacion_alta,
            'selfcare_restantes': selfcare_restantes,
            'pendientes_count': pendientes_count,
            'ultimas_ausencias': ultimas_ausencias,
            'payslip_count': payslip_count,
            'ultimo_payslip': ultimo_payslip,
        })

    def _get_recent_notifications(self, empleado, days=30, limit=20):
        """Feed de notificaciones del empleado: solicitudes de ausencia y de
        anticipo/préstamo que cambiaron de estado (aprobadas/rechazadas)
        recientemente. No usa un modelo nuevo, solo lee el estado y la
        fecha de última modificación de lo que ya existe."""
        since = datetime.now() - timedelta(days=days)
        notifications = []

        leaves = request.env['hr.leave'].sudo().search([
            ('employee_id', '=', empleado.id),
            ('state', 'in', ('validate', 'refuse')),
            ('write_date', '>=', since),
        ], order='write_date desc', limit=limit)
        for lv in leaves:
            notifications.append({
                'date': lv.write_date,
                'icon': 'fa-check-circle text-success' if lv.state == 'validate' else 'fa-times-circle text-danger',
                'title': 'Ausencia aprobada' if lv.state == 'validate' else 'Ausencia rechazada',
                'description': '%s (%s)' % (lv.holiday_status_id.name, lv.name or ''),
                'url': '/leave/user',
            })

        loans = request.env['hr.payslip.loans'].sudo().search([
            ('employee_id', '=', empleado.id),
            ('state', 'in', ('approved', 'paid')),
            ('write_date', '>=', since),
        ], order='write_date desc', limit=limit)
        for loan in loans:
            notifications.append({
                'date': loan.write_date,
                'icon': 'fa-check-circle text-success' if loan.state == 'approved' else 'fa-money text-info',
                'title': 'Anticipo aprobado' if loan.state == 'approved' else 'Anticipo pagado',
                'description': loan.name,
                'url': '/loan/user',
            })

        notifications.sort(key=lambda n: n['date'], reverse=True)
        return notifications[:limit]

    @http.route('/notifications', type='http', auth='user', website=True)
    def notifications(self, **post):
        empleado = self._get_employee()
        items = self._get_recent_notifications(empleado) if empleado else []
        return request.render("website_ausencias_19e.notifications_template", {
            'employee': empleado,
            'items': items,
        })

    @http.route('/employee/certificate', type='http', auth='user', website=True)
    def employee_certificate(self, **post):
        empleado = self._get_employee()
        if not empleado:
            return request.not_found()
        pdf_content, _content_type = request.env['ir.actions.report'].sudo()._render_qweb_pdf(
            'l10n_ec_hr_payroll_19e.action_report_hr_employee_certificate', [empleado.id]
        )
        pdfhttpheaders = [('Content-Type', 'application/pdf'), ('Content-Length', len(pdf_content))]
        return request.make_response(pdf_content, headers=pdfhttpheaders)

    @http.route('/employee/cargas-familiares', type='http', auth='user', website=True)
    def employee_cargas_familiares(self, **post):
        empleado = self._get_employee()
        return request.render("website_ausencias_19e.employee_cargas_familiares_template", {
            'employee': empleado,
        })

    @http.route('/loan/request', type='http', auth='user', website=True)
    def loan_request_form(self, **post):
        empleado = self._get_employee()
        return request.render("website_ausencias_19e.loan_request_template", {
            'employee': empleado,
        })

    @http.route('/loan/request/submit', type='http', auth='user', methods=['POST'], website=True)
    def loan_request_submit(self, **post):
        empleado = self._get_employee()
        if not empleado:
            return request.render("website_ausencias_19e.loan_request_template", {
                'employee': empleado,
                'error': 'No se encontró un empleado asociado a tu usuario.',
            })
        try:
            amount = float(post.get('amount') or 0)
            dues = int(post.get('dues') or 0)
            motivo = (post.get('motivo') or '').strip()
        except ValueError:
            amount, dues, motivo = 0, 0, ''

        if amount <= 0 or dues <= 0 or not motivo:
            return request.render("website_ausencias_19e.loan_request_template", {
                'employee': empleado,
                'error': 'Completa el motivo, un monto y un número de cuotas válidos.',
            })

        loan = request.env['hr.payslip.loans'].sudo().create({
            'name': motivo,
            'number': 'SOL-%s-%s' % (empleado.id, datetime.now().strftime('%Y%m%d%H%M%S')),
            'employee_id': empleado.id,
            'amount': amount,
            'dues': dues,
        })

        try:
            admin_users = request.env['res.users'].sudo().search([('is_configured', '=', True)])
            admin_emails = [e for e in [self._get_user_email(a) for a in admin_users] if e]
            if admin_emails:
                mail_content = (
                    "<h2>Nueva solicitud de anticipo/préstamo</h2>"
                    "Solicitante: " + str(empleado.name) + "<br/>"
                    "Área: " + str(empleado.department_id.name or '') + "<br/>"
                    "Monto solicitado: $ " + ("%.2f" % amount) + "<br/>"
                    "Cuotas: " + str(dues) + "<br/>"
                    "Motivo: " + motivo
                )
                self._send_mail({
                    'subject': 'Nueva solicitud de anticipo - %s' % empleado.name,
                    'body_html': mail_content,
                    'email_to': ','.join(admin_emails),
                })
        except Exception:
            _logger.exception("Error al notificar la solicitud de préstamo %s", loan.id)

        return request.render("website_ausencias_19e.loan_request_success_template", {'employee': empleado})

    @http.route(['/loan/user', '/loan/user/page/<int:page>'], type='http', auth='user', website=True)
    def loan_user_list(self, page=1, **post):
        empleado = self._get_employee()
        loans = request.env['hr.payslip.loans'].sudo().search(
            [('employee_id', '=', empleado.id)], order='application_date desc'
        ) if empleado else request.env['hr.payslip.loans']

        per_page = 5
        total_pages = ceil(len(loans) / per_page) if loans else 1
        page = min(max(1, page), total_pages)
        offset = (page - 1) * per_page
        pager = request.website.pager(url="/loan/user", total=total_pages, page=page, step=1)
        loans_page = loans[offset: offset + per_page]

        return request.render("website_ausencias_19e.loan_user_template", {
            'employee': empleado,
            'values': loans_page,
            'pager': pager,
        })

    @http.route(['/customer/form'], type='http', auth="user", website=True)
    def partner_form(self, **post,):
        empleado = self._get_employee()
        leave = self._get_leave_types(empleado)

        return request.render("website_ausencias_19e.tmp_customer_form", {'email': request.env.user.login, 'name': empleado.name, 'employee': empleado, 'departments': empleado.department_id, 'leave_type': leave})

    @http.route(['/customer/form/submit'], type='http', auth='user', website=True)
    #next controller with url for submitting data from the form#
    def customer_form_submit(self, **post):
        employee_id = self._get_employee()
        leave = self._get_leave_types(employee_id)


        if not employee_id:

            return request.render("website_ausencias_19e.tmp_customer_form", {'error': 'Ingrese una dirección de Correo Valida', 'departments': employee_id.department_id, 'leave_type': leave, 'email': request.env.user.login, 'name': employee_id.name, 'employee': employee_id})
        else:
            try:
                hora=datetime.strptime(post.get('De'), '%Y-%m-%d')
                hora_fin=datetime.strptime(post.get('Hasta'), '%Y-%m-%d')
                archivosubido = request.httprequest.files.get('att')
                try:
                    # Nota: los ids de los <select> llegan como texto desde el
                    # formulario HTML; convertirlos a int aquí evita un
                    # MissingError intermitente más adelante en el create()
                    # de hr.leave (el ORM cachea distinto un id-string vs.
                    # el mismo id ya prefetcheado como entero en la misma
                    # transacción, y una lectura interna del core deja de
                    # encontrar el registro).
                    partner = request.env['hr.leave'].sudo().create({
                    'holiday_type': 'employee',
                    'department_id': int(post.get('departments')) if post.get('departments') else False,
                    'employee_id': employee_id.id,
                    'date_from': hora.replace(hour=8, minute=0, second=0),
                    'date_to':  hora_fin.replace(hour=18, minute=0, second=0),
                    'request_date_from':  datetime.combine(hora,time.min),
                    'request_date_to':  datetime.combine(hora_fin,time.max),
                    'name': post.get('Motivo Permiso'),
                    'holiday_status_id': int(post.get('leave_type')) if post.get('leave_type') else False,
                    'state': 'confirm',
                    })
                    if archivosubido:
                        file_name = archivosubido.filename
                        Attachment = request.env['ir.attachment']
                        file = post.get('att')
                        attachment_id = Attachment.sudo().create({
                        'name': file_name,
                        'type': 'binary',
                        'datas': base64.b64encode(file.read()),
                        'res_model': request.env['hr.leave']._name,
                        'res_id':partner.id,
                        })
                        partner.sudo().write({'file': attachment_id.datas})
                        partner.sudo().write({'attachment': attachment_id.id})

                    leave_type = request.env['hr.leave.type'].sudo().search(
                        [('id', '=', post.get('leave_type'))], limit=1)
                except Exception as e:
                    _logger.exception("Error al crear la solicitud de ausencia para %s", employee_id.name)
                    return request.render("website_ausencias_19e.tmp_customer_form", {'error': 'Error al enviar la solicitud', 'departments': employee_id.department_id, 'leave_type': leave, 'email': request.env.user.login, 'name': employee_id.name, 'employee': employee_id})
                if partner:
                    try:
                        leave=request.env['hr.leave'].sudo()
                        base=request.env['ir.config_parameter'].sudo().get_param('web.base.url')
                        base+= '/web#id=%d&view_type=form&model=%s' % (partner.id,leave._name)
                        admin_users=request.env['res.users'].sudo().search([('is_configured','=',True)])
                        admin_emails = [email for email in [self._get_user_email(admin) for admin in admin_users] if email]
                        if not admin_emails:
                            raise Exception('No hay usuarios configurados con correo para recibir notificaciones de ausencias')
                        employee_email = employee_id.work_email if employee_id.work_email and email_split(employee_id.work_email) else False
                        if not employee_email:
                            raise Exception('El empleado no tiene un correo de trabajo valido')
                        # ADMIN DE RRHH
                        mail_content_admin = "<h1><center>SOLICITUD DE AUSENCIAS</center></h1> <br/>"+"Ha recibido una solicitud de ausencia <br/> "+"Solicitante:"+str(employee_id.name)+"<br/>"+"Area:"+str(employee_id.department_id.name)+"<br/>"+"Tipo de permiso:"+str(leave_type.name)+"<br/>"+"De: "+str(post.get(
                            'De'))+"<br/>"+"Hasta: "+str(post.get('Hasta'))+"<br/>" + "Motivo: "+str(post.get('Motivo Permiso'))+"<br/>"+"Atentamente,<br/>"+"<br/>"+"<center>Sistema de Ausencias <br/><a href='"+str(base)+"' class='btn btn-default'>APROBAR/NEGAR</a></center>"
                        main_content_admin = {
                            'subject': "Solicitud de Ausencia ",
                            'author_id': request.env.user.partner_id.id,
                            'body_html': mail_content_admin,
                            'email_to': ','.join(admin_emails),
                        }

                        mail_content = " <h1><center>SOLICITUD DE AUSENCIAS</center></h1> <br/>"+ "<br/> "+"Solicitante:"+str(employee_id.name)+"<br/>"+"Area:"+str(employee_id.department_id.name)+"<br/>"+"Tipo de permiso:"+str(leave_type.name)+"<br/>"+"De: "+str(post.get(
                            'De'))+"<br/>"+"Hasta: "+str(post.get('Hasta'))+"<br/>" + "Motivo: "+str(post.get('Motivo Permiso'))+"<br/>"+"Atentamente,<br/>"+"<br/>"+"<center>Sistema de Ausencias</center>"
                        main_content = {
                            'subject': "Solicitud de Ausencia enviada Exitosamente  ",
                            'author_id': request.env.user.partner_id.id,
                            'body_html': mail_content,
                            'email_to': employee_email,
                        }
                        #
                        try:
                            self._send_mail(main_content_admin)
                            self._send_mail(main_content)
                            return request.render("website_ausencias_19e.tmp_customer_form_success", {'mensaje': 'Solicitud enviada correctamente', 'employee': employee_id})
                        except Exception as e:
                            _logger.exception("Error al enviar el correo de notificación de ausencia (id=%s)", partner.id)
                            partner.unlink()
                            return request.render("website_ausencias_19e.tmp_customer_form", {'error': 'Error al enviar la solicitud', 'departments': employee_id.department_id, 'leave_type': leave, 'email': request.env.user.login, 'name': employee_id.name, 'employee': employee_id})
                    except Exception as e:
                        _logger.exception("Error al preparar la notificación de ausencia (id=%s)", partner.id)
                        partner.unlink()
                        return request.render("website_ausencias_19e.tmp_customer_form", {'error': e, 'departments': employee_id.department_id, 'leave_type': leave, 'email': request.env.user.login, 'name': employee_id.name, 'employee': employee_id})
            except Exception as e:
                _logger.exception("Error inesperado al cargar el formulario de ausencia para %s", employee_id.name)
                return request.render("website_ausencias_19e.tmp_customer_form", {'error': 'Error al cargar formulario', 'departments': employee_id.department_id, 'leave_type': leave, 'email': request.env.user.login, 'name': employee_id.name, 'employee': employee_id})


    @http.route(['/payslip/form','/payslip/form/page/<int:page>'], type='http', auth="user", website=True)
    def payslip_form(self, page=1, search='', anio='', **post):
        empleado = self._get_employee()
        if empleado.contract_type == '2':
            payslip = request.env['hr.payslip'].sudo()
            anios_disponibles = []
        else:
            domain = [('employee_id', '=', empleado.id), ('state', 'in', ('validated', 'paid'))]
            if anio and anio.isdigit():
                domain += [
                    ('date_from', '>=', '%s-01-01' % anio),
                    ('date_from', '<=', '%s-12-31' % anio),
                ]
            payslip = request.env['hr.payslip'].sudo().search(domain, order='date_from desc')
            anios_disponibles = sorted({
                p.date_from.year for p in
                request.env['hr.payslip'].sudo().search([
                    ('employee_id', '=', empleado.id), ('state', 'in', ('validated', 'paid'))])
                if p.date_from
            }, reverse=True)

        per_page = 5  # Número de registros por página
        total_len = len(payslip)
        total_pages = ceil(total_len / per_page)

        # Asegúrate de que la página esté dentro del rango válido
        page = min(max(1, page), total_pages)

        # Calcular el offset para la paginación
        offset = (page - 1) * per_page

        # Obtener la información del paginador
        pager = request.website.pager(
            url="/payslip/form",
            total=total_pages,
            page=page,
            step=1,
            url_args={'anio': anio},
        )

        # Obtener las ausencias para la página actual
        payslip = payslip[offset: offset + per_page]

        return request.render("website_ausencias_19e.payslips_reports", {
            'values': payslip,
            'pager': pager,
            'employee': empleado,
            'anio': anio,
            'anios_disponibles': anios_disponibles,
        })

    @http.route('/report/<int:partner_id>', type='http', auth='user', website=False)
    def payslip_report(self, partner_id):
        payslip = request.env['hr.payslip'].sudo().browse(partner_id)
        if not payslip.exists():
            return request.not_found()
        empleado = self._get_employee()
        is_owner = empleado and payslip.employee_id.id == empleado.id
        is_hr = request.env.user.has_group('l10n_ec_hr_payroll_19e.group_hr_payroll_user')
        if not (is_owner or is_hr):
            return request.not_found()
        value = payslip.print()
        try:
            pdfhttpheaders = [('Content-Type', 'application/pdf'), ('Content-Length', len(value[0]))]
            return request.make_response(value[0], headers=pdfhttpheaders)
        except Exception:
            return request.render("website_ausencias_19e.payslips_reports", {'values': payslip, 'employee': empleado})


    @http.route(['/leave/user', '/leave/user/page/<int:page>'], type='http', auth='user', website=True)
    def list_leave(self, page=1, search='', anio='', estado='', **post):
        empleado = self._get_employee()

        # Todas las solicitudes del empleado (pendientes, aprobadas,
        # rechazadas), no solo las aprobadas: antes las pendientes eran
        # invisibles para el propio empleado en "Mis ausencias".
        domain = [('employee_id', '=', empleado.id), ('state', '!=', 'cancel')]
        if estado:
            domain.append(('state', '=', estado))
        if anio and anio.isdigit():
            domain += [
                ('request_date_from', '>=', '%s-01-01' % anio),
                ('request_date_from', '<=', '%s-12-31' % anio),
            ]
        leave = request.env['hr.leave'].sudo().search(domain, order='request_date_from desc')

        # Años disponibles para el desplegable de filtro (a partir de todas
        # las solicitudes del empleado, sin aplicar el propio filtro).
        anios_disponibles = sorted({
            lv.request_date_from.year for lv in
            request.env['hr.leave'].sudo().search([
                ('employee_id', '=', empleado.id), ('state', '!=', 'cancel')])
            if lv.request_date_from
        }, reverse=True)

        combinado = self._get_vacation_summary(empleado)

        per_page = 5  # Número de registros por página
        total_len = len(leave)
        total_pages = ceil(total_len / per_page)

        # Asegúrate de que la página esté dentro del rango válido
        page = min(max(1, page), total_pages)

        # Calcular el offset para la paginación
        offset = (page - 1) * per_page

        # Obtener la información del paginador
        pager = request.website.pager(
            url="/leave/user",
            total=total_pages,
            page=page,
            step=1,
            url_args={'anio': anio, 'estado': estado},
        )

        # Obtener las ausencias para la página actual
        leave_page = leave[offset: offset + per_page]

        return request.render("website_ausencias_19e.leave_list", {
            'values': leave_page,
            'historic': combinado,
            'pager': pager,
            'employee': empleado,
            'anio': anio,
            'estado': estado,
            'anios_disponibles': anios_disponibles,
        })

    @http.route('/leave/cancel/<int:leave_id>', type='http', auth='user', methods=['POST'], website=True, csrf=True)
    def leave_cancel(self, leave_id):
        """Permite al empleado cancelar su propia solicitud mientras esté
        pendiente de aprobación (no se puede cancelar algo ya aprobado o
        rechazado, ni la solicitud de otro empleado)."""
        empleado = self._get_employee()
        leave = request.env['hr.leave'].sudo().browse(leave_id)
        if leave.exists() and empleado and leave.employee_id.id == empleado.id and leave.state == 'confirm':
            leave.sudo().action_cancel() if hasattr(leave, 'action_cancel') else leave.sudo().write({'state': 'cancel'})
        return request.redirect('/leave/user')

    @http.route('/calendar/leave', type='http', auth='user', website=True)
    def team_leave_calendar(self, **post):
        empleado = self._get_employee()
        leave = request.env['hr.leave'].sudo().search([('state', '=', 'validate'),('employee_id','!=',empleado.id)] ,limit=10,order='request_date_from desc')
        return request.render("website_ausencias_19e.leave_list_all", {'values': leave, 'employee': empleado})

    def _get_antiguedad(self, empleado):
        """Texto legible de la antigüedad del empleado a partir de su fecha
        de ingreso (años y meses completos)."""
        if not empleado.date_of_admission:
            return False
        hoy = datetime.now().date()
        ingreso = empleado.date_of_admission
        meses_totales = (hoy.year - ingreso.year) * 12 + (hoy.month - ingreso.month)
        if hoy.day < ingreso.day:
            meses_totales -= 1
        meses_totales = max(meses_totales, 0)
        anios, meses = divmod(meses_totales, 12)
        partes = []
        if anios:
            partes.append('%d año%s' % (anios, 's' if anios != 1 else ''))
        if meses or not partes:
            partes.append('%d mes%s' % (meses, 'es' if meses != 1 else ''))
        return ' y '.join(partes)

    @http.route('/customer/form-update', type='http', auth='user', website=True)
    def customer_form_update(self, **post):
        empleado = self._get_employee()
        civil_state={
            'single':'Soltero',
            'married':'Casado',
            'widower':'Viudo',
            'divorced':'Divorciado',
            'cohabitant':'Cohabitante Legal',
            'union_fact':'Unión de Hecho',
        }
        contract_type_labels = {
            '1': 'Nómina',
            '2': 'Prestación de servicios',
            '3': 'C-Level',
        }

        return request.render("website_ausencias_19e.employee_info_template", {
            'employee': empleado,
            'civil': civil_state,
            'antiguedad': self._get_antiguedad(empleado) if empleado else False,
            'contract_type_label': contract_type_labels.get(empleado.contract_type) if empleado else False,
        })

    @http.route('/employee/documents', type='http', auth='user', website=True)
    def employee_documents(self, **post):
        empleado = self._get_employee()
        documents = request.env['ir.attachment'].sudo().search([
            ('res_model', '=', 'hr.employee'),
            ('res_id', '=', empleado.id),
            ('res_field', '=', False),
        ], order='create_date desc') if empleado else request.env['ir.attachment']
        return request.render("website_ausencias_19e.employee_documents_template", {
            'employee': empleado,
            'documents': documents,
        })

    @http.route('/employee/documents/<int:attachment_id>', type='http', auth='user', website=True)
    def employee_document_download(self, attachment_id):
        empleado = self._get_employee()
        attachment = request.env['ir.attachment'].sudo().browse(attachment_id)
        if not (empleado and attachment.exists() and attachment.res_model == 'hr.employee'
                and attachment.res_id == empleado.id):
            return request.not_found()
        return request.env['ir.binary']._get_stream_from(attachment).get_response(as_attachment=True)

    @http.route('/employee/form/save', type='http', auth='user', methods=['POST'], website=True)
    def employee_form_save(self, **post):
        employee = self._get_employee()
        if not employee:
            return request.redirect('/customer/form-update')

        employee.sudo().write({
            'name': post.get('name'),
            'emergency_contact': post.get('emergency_contact'),
            'emergency_phone': post.get('emergency_phone'),
            'marital': post.get('marital'),
            'children': post.get('children')
        })

        employee.partner_id.sudo().write({'street':post.get('street'),'street2':post.get('street2'),'city':post.get('city')})
        return request.redirect('/customer/form-update')

from datetime import datetime, time
from datetime import datetime
from typing import DefaultDict
from datetime import datetime, date as dt
from html import escape as _html_escape
import logging
from odoo import _, api, exceptions, fields, models
from odoo.exceptions import UserError, ValidationError
from datetime import timedelta
from math import floor

_logger = logging.getLogger(__name__)


def _esc(value):
    """Escapa texto de empleado/usuario antes de insertarlo en un body_html
    armado a mano, para evitar que un nombre, motivo u otro campo libre
    inyecte HTML en el correo de notificación."""
    return _html_escape(str(value or ''))

class HrDepartment(models.Model):
    _inherit = "hr.department"
    _description = "Department"

    manager_id_web = fields.Many2one(
        "res.users",
        string="Manager Web",
        domain=lambda self: [("group_ids", "=", self.env.ref("website_ausencias_19e.group_hr_payroll_user_manager_leave").id)]
    )


class HrEmployee(models.Model):
    _inherit = "hr.employee"
    _description = "MANAGER WEB"

    manager_id_web = fields.Many2one(
        "res.users",
        string="Manager Web",
        domain=lambda self: [("group_ids", "=", self.env.ref("website_ausencias_19e.group_hr_payroll_user_manager_leave").id)]
    )


class ResUsers(models.Model):
    _inherit = 'res.users'

    department_id = fields.Many2one("hr.department", string="Department")


class HrManagerLeave(models.Model):
    _name = "hr.manager.leave"

    name = fields.Char(string="Nombre", related="leave_id.employee_id.name")
    leave_id = fields.Many2one("hr.leave", string="Ausencia")
    description = fields.Text(string="Descripción")
    state = fields.Selection(
        [('draft', 'Por Aprobar'), ('approved', 'Aprobado'), ('reject', 'Negado')],
        string='Estado',
        readonly=True,
        default='draft',
        tracking=True
    )
    employee_id = fields.Many2one("hr.employee", string="Empleado")
    date_from = fields.Date(string="Desde")
    date_to = fields.Date(string="Hasta")
    number_of_days = fields.Float(string="Número de días")
    leave_type = fields.Many2one("hr.leave.type", string="Tipo de Ausencia")
    department_id = fields.Many2one("hr.department", string="Departamento")
    manager_id = fields.Many2one("res.users", string="Jefe de Area")
    duration_display = fields.Char(string="Duración", compute="_compute_duration_display")

    @api.depends("number_of_days")
    def _compute_duration_display(self):
        for rec in self:
            days = rec.number_of_days or 0.0
            n = int(days) if days == int(days) else round(days, 1)
            rec.duration_display = "%s día%s" % (n, "" if n == 1 else "s")

    def aprobar(self):
        for a in self:
            a.leave_id.sudo().write({'state': 'validate1', 'validate_ares': True})
            a.sudo().write({'state': 'approved'})

            admin_rhh = self.env['res.users'].sudo().search([('is_configured', '=', True)])
            if not admin_rhh:
                continue
            admin = self.env['hr.leave'].sudo()
            base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
            base_url += '/web#id=%d&view_type=form&model=%s' % (a.leave_id.id, admin._name)
            mail_content = (
                " <h1><center>SOLICITUD DE AUSENCIAS</center></h1><br/> "
                "La solicitud ha sido APROBADA por " + _esc(self.env.user.name or self.env.user.login) + "<br/>"
                "<br/>Solicitante:" + _esc(a.employee_id.name) + "<br/>"
                "Area:" + _esc(a.employee_id.department_id.name) + "<br/>"
                "Fecha de Inicio:" + _esc(a.date_from) + "<br/>"
                "Fecha de Fin:" + _esc(a.date_to) + "<br/>"
                "Tipo de Ausencia:" + _esc(a.leave_type.name) + "<br/>"
                "Estado:APROBADO POR JEFE DE AREA<br/><br/>"
                "<center><a href='" + str(base_url) + "'class='btn btn-default'>VALIDAR</a></center>"
            )
            # Un solo correo con todos los admins en copia, en vez de
            # sobreescribir main_content en cada vuelta del bucle (antes
            # solo se enviaba al último admin de la lista).
            main_content = {
                'subject': "Solicitud de Ausencia  ",
                'body_html': mail_content,
                'email_to': ','.join(admin_rhh.mapped('login')),
            }
            try:
                self.env['mail.mail'].sudo().create(main_content).send()
            except Exception:
                raise ValidationError(_('Error al enviar correo'))

    def rechazar(self):
        for a in self:
            # 'leave_id.state' no es un campo válido de hr.manager.leave: ese
            # write() lanzaba ValueError y el botón "Rechazar" del jefe de
            # área terminaba en un error 500 en vez de rechazar la solicitud.
            a.leave_id.sudo().write({'state': 'refuse', 'validate_ares': False})
            a.sudo().write({'state': 'reject'})

            admin_rhh = self.env['res.users'].sudo().search([('is_configured', '=', True)])
            if not admin_rhh:
                continue
            admin = self.env['hr.leave'].sudo()
            base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
            base_url += '/web#id=%d&view_type=form&model=%s' % (a.leave_id.id, admin._name)
            mail_content = (
                " <h1><center>SOLICITUD DE AUSENCIAS</center></h1> <br/> <br/> "
                "La solicitud ha sido Rechazada  por " + _esc(self.env.user.name or self.env.user.login) + "<br/> "
                "Solicitante:" + _esc(a.employee_id.name) + "<br/>"
                "Area:" + _esc(a.employee_id.department_id.name) + "<br/>"
                "Fecha de Inicio:" + _esc(a.date_from) + "<br/>"
                "Fecha de Fin:" + _esc(a.date_to) + "<br/>"
                "Tipo de Ausencia:" + _esc(a.leave_type.name) + "<br/>"
                "Estado:NEGADO POR JEFE DE AREA<br/><br/>"
                "<center><a href='" + str(base_url) + "'class='btn btn-default'>VER SOLICITUD</a></center>"
            )
            main_content = {
                'subject': "Solicitud de Ausencia",
                'body_html': mail_content,
                'email_to': ','.join(admin_rhh.mapped('login')),
            }
            try:
                self.env['mail.mail'].sudo().create(main_content).send()
            except Exception:
                raise ValidationError(_('Error al enviar correo'))


class HrHolidays(models.Model):
    _inherit = "hr.leave"

    validate_ares = fields.Boolean(string="Validar", default=False)
    file = fields.Binary(string="Adjunto")
    attachment = fields.Many2one("ir.attachment", string="Adjunto")

    def _notify_rrhh_no_manager(self):
        """Política: cuando el empleado no tiene jefe inmediato (Manager Web)
        configurado, la solicitud pasa directo a RRHH en vez de bloquear la
        aprobación — antes esto lanzaba un error y la ausencia quedaba
        atascada sin que nadie pudiera aprobarla ni notificarla. No crea un
        hr.manager.leave (no hay jefe al que asignárselo); el aviso a RRHH
        es solo informativo, la validación final ya la hacen ellos mismos
        desde el módulo estándar de Ausencias."""
        self.ensure_one()
        admin_rhh = self.env['res.users'].sudo().search([('is_configured', '=', True)])
        if not admin_rhh:
            return
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        mail_content = (
            " <h1><center>SOLICITUD DE AUSENCIAS</center></h1> <br/>"
            "Solicitante:" + _esc(self.employee_id.name) + "<br/>"
            "Area:" + _esc(self.employee_id.department_id.name) + "<br/>"
            "Fecha de Inicio:" + _esc(self.date_from) + "<br/>"
            "Fecha de Fin:" + _esc(self.date_to) + "<br/>"
            "Tipo de Ausencia:" + _esc(self.holiday_status_id.name) + "<br/>"
            "Este empleado no tiene jefe inmediato asignado, así que la solicitud pasa directo a RRHH.<br/><br/>"
            "<center><a href='" + str(base_url) + "/odoo/time-off'class='btn btn-default'>REVISAR EN ODOO</a></center>"
        )
        try:
            self.env['mail.mail'].sudo().create({
                'subject': "Solicitud de Ausencia sin jefe inmediato: PARA REVISIÓN DE RRHH",
                'body_html': mail_content,
                'email_to': ','.join(admin_rhh.mapped('login')),
            }).send()
        except Exception:
            # No bloquea la aprobación por un fallo de correo: el cron
            # check_pending_leave_reminders ya avisa a diario si esta
            # solicitud queda atascada sin resolver.
            _logger.exception("Error al notificar a RRHH la ausencia %s (sin jefe inmediato)", self.id)

    def notificar(self):
        for a in self:
            if not a.employee_id.manager_id_web:
                a._notify_rrhh_no_manager()
                continue

            leave = self.env['hr.manager.leave'].sudo().search([('leave_id', '=', a.id)], limit=1)
            created_now = False
            if not leave:
                leave = self.env['hr.manager.leave'].sudo().create({
                    'department_id': a.department_id.id,
                    'employee_id': a.employee_id.id,
                    'date_from': a.date_from,
                    'date_to': a.date_to,
                    'number_of_days': a.number_of_days,
                    'description': a.name,
                    'leave_type': a.holiday_status_id.id,
                    'state': 'draft',
                    'leave_id': a.id,
                    'manager_id': a.employee_id.manager_id_web.id,
                })
                created_now = True

            try:
                admin = self.env['hr.manager.leave'].sudo()
                base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
                base_url += '/web#id=%d&view_type=form&model=%s' % (leave.id, admin._name)
                mail_content = (
                    " <h1><center>SOLICITUD DE AUSENCIAS</center></h1> <br/>"
                    "Solicitante:" + _esc(a.employee_id.name) + "<br/>"
                    "Area:" + _esc(a.employee_id.department_id.name) + "<br/>"
                    "Fecha de Inicio:" + _esc(a.date_from) + "<br/>"
                    "Fecha de Fin:" + _esc(a.date_to) + "<br/>"
                    "Tipo de Ausencia:" + _esc(a.holiday_status_id.name) + "<br/>"
                    "Estado:APROBADO POR RECURSOS HUMANOS<br/><br/>"
                    "<center><a href='" + str(base_url) + "'class='btn btn-default'>APROBAR/NEGAR</a></center>"
                )
                main_content = {
                    'subject': "Solicitud de Ausencia:PARA REVISION",
                    'body_html': mail_content,
                    'email_to': a.employee_id.manager_id_web.login,
                }
                self.env['mail.mail'].sudo().create(main_content).send()
            except Exception:
                if created_now:
                    leave.unlink()
                raise UserError(_("Error no se pudo enviar el mail."))

    def action_super_approve(self):
        self.ensure_one()
        self.state = 'validate'

    def action_approve(self, context=None):
        """ This method is called when a holiday request is approved by manager. """
        self.ensure_one()
        if not self.employee_id.manager_id_web:
            # Sin jefe inmediato: la solicitud pasa directo a RRHH en vez de
            # bloquear la aprobación (ver _notify_rrhh_no_manager).
            self.state = 'validate1'
            self._notify_rrhh_no_manager()
            return

        # Idempotencia: si ya existe un aviso al jefe de área para esta
        # misma ausencia (p. ej. porque action_approve() se disparó más de
        # una vez -algunos tipos de ausencia "sin validación" se
        # auto-aprueban al crearse y luego alguien vuelve a aprobar a mano-)
        # no se duplica el registro ni se reenvía el correo.
        if self.env['hr.manager.leave'].sudo().search_count([('leave_id', '=', self.id)]):
            self.state = 'validate1'
            return

        previous_state = self.state
        self.state = 'validate1'
        manager_registry = self.env['hr.manager.leave']
        try:
            manager_registry = self.env['hr.manager.leave'].sudo().create({
                'department_id': self.department_id.id,
                'employee_id': self.employee_id.id,
                'date_from': self.date_from,
                'date_to': self.date_to,
                'number_of_days': self.number_of_days,
                'description': self.name,
                'leave_type': self.holiday_status_id.id,
                'state': 'draft',
                'leave_id': self.id,
                'manager_id': self.employee_id.manager_id_web.id,
            })
            admin = self.env['hr.manager.leave'].sudo()
            base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
            base_url += '/web#id=%d&view_type=form&model=%s' % (manager_registry.id, admin._name)
            mail_content = (
                " <h1><center>SOLICITUD DE AUSENCIAS</center></h1> <br/>"
                "Solicitante:" + _esc(self.employee_id.name) + "<br/>"
                "Area:" + _esc(self.employee_id.department_id.name) + "<br/>"
                "Fecha de Inicio:" + _esc(self.date_from) + "<br/>"
                "Fecha de Fin:" + _esc(self.date_to) + "<br/>"
                "Tipo de Ausencia:" + _esc(self.holiday_status_id.name) + "<br/>"
                "Estado:APROBADO POR RECURSOS HUMANOS<br/><br/>"
                "<center><a href='" + str(base_url) + "'class='btn btn-default'>APROBAR/NEGAR</a></center>"
            )
            main_content = {
                'subject': "Solicitud de Ausencia:PARA REVISION",
                'body_html': mail_content,
                'email_to': self.employee_id.manager_id_web.login,
            }
            self.env['mail.mail'].sudo().create(main_content).send()

        except Exception:
            manager_registry.unlink()
            self.state = previous_state
            raise UserError(_("Error no se pudo enviar el mail de notificación al jefe inmediato."))

    def action_validate(self):
        current_employee = self.env['hr.employee'].search([('user_id', '=', self.env.uid)], limit=1)
        if any(holiday.state not in ['validate1'] for holiday in self):
            raise UserError(_('Leave request must be confirmed in order to approve it.'))

        self.write({'state': 'validate'})
        self.filtered(lambda holiday: holiday.validation_type == 'both').write({'second_approver_id': current_employee.id})
        self.filtered(lambda holiday: holiday.validation_type != 'both').write({'first_approver_id': current_employee.id})

        for holiday in self.filtered(lambda holiday: holiday.holiday_type != 'employee'):
            if holiday.holiday_type == 'category':
                employees = holiday.category_id.employee_ids
            elif holiday.holiday_type == 'company':
                employees = self.env['hr.employee'].search([('company_id', '=', holiday.mode_company_id.id)])
            else:
                employees = holiday.department_id.member_ids

            if self.env['hr.leave'].search_count([
                ('date_from', '<=', holiday.date_to),
                ('date_to', '>', holiday.date_from),
                ('state', 'not in', ['cancel', 'refuse']),
                ('holiday_type', '=', 'employee'),
                ('employee_id', 'in', employees.ids)
            ]):
                raise ValidationError(_('You can not have 2 leaves that overlaps on the same day.'))

            values = [holiday.sudo()._prepare_holiday_values(employee) for employee in employees]
            leaves = self.env['hr.leave'].with_context(
                tracking_disable=True,
                mail_activity_automation_skip=True,
                leave_fast_create=True,
            ).create(values)
            leaves.sudo().action_approve()
            if leaves and leaves[0].validation_type == 'both':
                leaves.sudo().action_validate()

        employee_requests = self.filtered(lambda hol: hol.holiday_type == 'employee')
        employee_requests.sudo()._validate_leave_request()
        if not self.env.context.get('leave_fast_create'):
            employee_requests.sudo().activity_update()

        if self.state == 'validate' and self.employee_id.work_email:
            # Notifica siempre al empleado que su solicitud fue aprobada,
            # sin importar qué jefe/RRHH fue quien la aprobó (antes solo se
            # enviaba si el aprobador coincidía exactamente con el usuario
            # marcado como "recibir notificaciones", así que casi nunca se
            # avisaba al empleado).
            mail_content = (
                " <h1><center>SOLICITUD DE AUSENCIAS</center></h1> <br/> "
                "La solicitud ha sido APROBADA por " + _esc(self.env.user.name or self.env.user.login) + "<br/>"
                "Motivo:" + _esc(self.report_note) + "<br/>"
                "Solicitante:" + _esc(self.employee_id.name) + "<br/>"
                "Area:" + _esc(self.employee_id.department_id.name) + "<br/>"
                "Fecha de Inicio:" + _esc(self.date_from) + "<br/>"
                "Fecha de Fin:" + _esc(self.date_to) + "<br/>"
                "Tipo de Ausencia:" + _esc(self.holiday_status_id.name) + "<br/>"
                "Estado:APROBADO<br/>"
                "<br/>Atentamente<br/>Sistema de Ausencias <br/> "
            )

            main_content = {
                'subject': "Solicitud de Ausencia:APROBADA",
                'body_html': mail_content,
                'email_to': self.employee_id.work_email,
            }
            self.env['mail.mail'].sudo().create(main_content).send()

        return True

    def action_refuse(self):
        res = super(HrHolidays, self).action_refuse()

        if self.state == 'refuse' and self.employee_id.work_email:
            # Ver nota equivalente en action_validate: se notifica siempre
            # al empleado, sin depender de quién hizo el rechazo.
            mail_content = (
                " <h1><center>SOLICITUD DE AUSENCIAS</center></h1> <br/> "
                "La solicitud ha sido Rechazada por " + _esc(self.env.user.name or self.env.user.login) + "<br/>"
                "Motivo:" + _esc(self.report_note) + "<br/>"
                "Solicitante:" + _esc(self.employee_id.name) + "<br/>"
                "Area:" + _esc(self.employee_id.department_id.name) + "<br/>"
                "Fecha de Inicio:" + _esc(self.date_from) + "<br/>"
                "Fecha de Fin:" + _esc(self.date_to) + "<br/>"
                "Tipo de Ausencia:" + _esc(self.holiday_status_id.name) + "<br/>"
                "Estado:RECHAZADO<br/>"
                "<br/>Atentamente<br/>Sistema de Ausencias <br/> "
            )

            main_content = {
                'subject': "Solicitud de Ausencia:RECHAZADA",
                'body_html': mail_content,
                'email_to': self.employee_id.work_email,
            }
            self.env['mail.mail'].sudo().create(main_content).send()
        return res

    def get_vacations(self, employee_id):
        base_prop = 0
        current_date = dt.today()

        # ============================================================
        # FREELANCE
        # ============================================================
        if employee_id.contract_type == '2':
            if not employee_id.date_initial:
                return 0

            days_of_service = (current_date - employee_id.date_initial).days

            if days_of_service <= 0:
                return 0

            proportional_days = (days_of_service * 15.0) / 360.0
            return floor(proportional_days)  # 🔥 CAMBIO

        # ============================================================
        # METODO 2
        # ============================================================
        if employee_id.method_calc == '2':
            if employee_id.date_initial:
                days_of_service = (current_date - employee_id.date_initial).days
                days_in_current_year = days_of_service % 360
                proportional_days = (days_in_current_year / 360.0) * 15.0
                return floor(proportional_days)  # 🔥 CAMBIO
            return 0

        # ============================================================
        # METODO 3
        # ============================================================
        if employee_id.method_calc == '3':
            if employee_id.date_initial:
                days_of_service = (current_date - employee_id.date_initial).days
                years_of_service = days_of_service // 360
                base_days = employee_id.days_initial + years_of_service
                days_in_current_year = days_of_service % 360
                proportional_days = ((days_in_current_year / 360.0) * base_days) + base_days
                return floor(proportional_days)  # 🔥 CAMBIO
            else:
                return 15

        # ============================================================
        # METODO NORMAL
        # ============================================================
        if employee_id.date_of_admission:
            years_of_service = (current_date - employee_id.date_of_admission).days / 365.0
            days_total = 0

            # 15 dias base + 1 dia adicional por cada anio despues del 5to,
            # con tope de 15 dias adicionales (maximo legal 30 dias/anio,
            # Art. 69 Codigo del Trabajo).
            for year in range(1, int(years_of_service) + 1):
                if year <= 5:
                    days_total += 15
                else:
                    days_total += 15 + min(year - 5, 15)

            remaining_year_fraction = years_of_service - int(years_of_service)

            if remaining_year_fraction > 0:
                if int(years_of_service) <= 5:
                    base_prop = 15
                else:
                    base_prop = 15 + min((int(years_of_service) + 1) - 5, 15)

                days_total += base_prop * remaining_year_fraction

            return floor(days_total)  # 🔥 CAMBIO CLAVE

        return 0

    @api.model
    def check_self_carea_day_absences(self):
        today = dt.today()
        year_start = dt(today.year, 1, 1)
        if today.month == 12:
            start_date = dt(today.year, 7, 1)
            end_date = today
        else:
            start_date = year_start
            end_date = dt(today.year, 6, 30)

        employees = self.env['hr.employee'].search([]).filtered(
            lambda x: x.status == 'active' and x.name != 'Administrator'
        )
        for employee in employees:
            absence = self.env['hr.leave'].search([
                ('employee_id', '=', employee.id),
                ('date_from', '>=', start_date),
                ('date_to', '<=', end_date),
                ('state', '=', 'validate'),
                ('holiday_status_id', '=', self.env.ref('hr_leave_type.leave_type_self').id)
            ])
            if absence:
                continue
            else:
                self.env['hr.leave'].with_context(
                    leave_skip_state_check=True, leave_skip_date_check=True
                ).create({
                    'employee_id': employee.id,
                    'holiday_status_id': self.env.ref('hr_leave_type.leave_type_self').id,
                    'request_date_from': end_date,
                    'request_date_to': end_date,
                    'date_from': end_date,
                    'date_to': end_date,
                    'number_of_days': 1,
                    'state': 'validate',
                    'holiday_type': 'employee',
                    'validation_type': 'both',
                })

    @api.model
    def check_pending_leave_reminders(self):
        """Envía a RRHH un recordatorio diario con las solicitudes de
        ausencia que llevan más de 2 días sin aprobarse ni rechazarse, para
        que no se queden atascadas sin que nadie lo note."""
        limit_date = dt.today() - timedelta(days=2)
        pending = self.search([
            ('state', 'in', ('confirm', 'validate1')),
            ('create_date', '<=', limit_date),
        ], order='create_date asc')
        if not pending:
            return

        admin_rhh = self.env['res.users'].sudo().search([('is_configured', '=', True)])
        if not admin_rhh:
            return

        rows = ''.join(
            "<tr>"
            "<td>" + _esc(lv.employee_id.name) + "</td>"
            "<td>" + _esc(lv.department_id.name) + "</td>"
            "<td>" + _esc(lv.holiday_status_id.name) + "</td>"
            "<td>" + _esc(lv.request_date_from) + " - " + _esc(lv.request_date_to) + "</td>"
            "<td>" + (lv.state == 'confirm' and 'Pendiente 1ra aprobación' or 'Pendiente validación RRHH') + "</td>"
            "</tr>"
            for lv in pending
        )
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        mail_content = (
            "<h1><center>SOLICITUDES DE AUSENCIA PENDIENTES</center></h1><br/>"
            "Hay " + str(len(pending)) + " solicitud(es) con más de 2 días sin resolver:<br/><br/>"
            "<table border='1' cellpadding='6' cellspacing='0' style='border-collapse:collapse;width:100%;'>"
            "<tr><th>Empleado</th><th>Área</th><th>Tipo</th><th>Periodo</th><th>Estado</th></tr>"
            + rows +
            "</table><br/>"
            "<center><a href='" + str(base_url) + "/odoo/time-off' class='btn btn-default'>Ver en Odoo</a></center>"
        )
        self.env['mail.mail'].sudo().create({
            'subject': "Recordatorio: %d solicitud(es) de ausencia pendiente(s)" % len(pending),
            'body_html': mail_content,
            'email_to': ','.join(admin_rhh.mapped('login')),
        }).send()


class ResUsers(models.Model):
    _inherit = 'res.users'

    is_configured = fields.Boolean(string='Recibir notificaciones de ausencias', default=False)

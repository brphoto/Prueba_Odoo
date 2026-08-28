# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError


class ChatroomChannel(models.Model):
    _inherit = 'chatroom.channel'

    meeting_count = fields.Integer(compute='_compute_meeting_data')
    next_meeting_date = fields.Datetime(compute='_compute_meeting_data')

    def action_create_meeting(self):
        """Crea una reunión nativa y devuelve su enlace sin enviarlo.

        Separar la creación del envío permite que el agente IA conserve el
        evento aunque WhatsApp esté fuera de horario, sin credenciales o
        requiera una plantilla. El envío se ejecuta después y queda
        trazable como una operación independiente.
        """
        self.ensure_one()
        if not self.partner_id:
            raise UserError(_("Esta conversación no tiene un contacto asociado."))
        now = fields.Datetime.now()
        event = self.env['calendar.event'].create({
            'name': _("Reunión con %s") % self.partner_id.name,
            'start': fields.Datetime.add(now, hours=1),
            'stop': fields.Datetime.add(now, hours=2),
            'partner_ids': [(6, 0, (self.partner_id | self.assigned_user_id.partner_id).ids)],
            'user_id': self.assigned_user_id.id or self.env.user.id,
            'description': self.ai_summary or '',
        })
        if not event.videocall_location:
            event._set_discuss_videocall_location()
        link = event.videocall_location
        if not link:
            raise UserError(_("No se pudo obtener el enlace de videollamada."))
        return {'event_id': event.id, 'link': link, 'name': event.name}

    def action_create_meet_and_send(self):
        """Crea el evento y envía el enlace generado al hilo.

        Si Google Calendar está sincronizado, Odoo conserva el enlace que
        devuelva la integración. En instalaciones sin Google se usa la
        videollamada nativa de Calendar como fallback operativo.
        """
        self.ensure_one()
        meeting = self.action_create_meeting()
        link = meeting['link']
        self.action_send_text(_("Te comparto el enlace para la reunión: %s") % link)
        return meeting

    def _get_meetings(self):
        """Reuniones de Calendario donde el contacto de esta conversación
        es invitado, más próximas primero. No hay un vínculo directo
        chatroom.channel -> calendar.event: se busca por partner_ids,
        igual criterio que usa chatroom_sales_intelligence para
        relacionar la conversación con la oportunidad del contacto."""
        self.ensure_one()
        if not self.partner_id:
            return self.env['calendar.event']
        return self.env['calendar.event'].search(
            [('partner_ids', 'in', self.partner_id.id)], order='start desc')

    def _compute_meeting_data(self):
        for channel in self:
            meetings = channel._get_meetings()
            channel.meeting_count = len(meetings)
            upcoming = meetings.filtered(
                lambda m: m.start and m.start >= fields.Datetime.now()).sorted('start')
            channel.next_meeting_date = upcoming[:1].start if upcoming else False

    def action_schedule_meeting(self):
        """Abre el formulario nativo de Calendario para agendar una
        reunión con el contacto de esta conversación (invitaciones,
        videollamada, recordatorios: todo lo nativo de 'calendar', no
        una versión reducida propia). No crea el evento solo: el
        agente elige fecha/hora y confirma desde el formulario real."""
        self.ensure_one()
        if not self.partner_id:
            raise UserError(_("Esta conversación no tiene un contacto asociado."))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'calendar.event',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {
                'default_name': _("Reunión con %s") % self.partner_id.name,
                'default_partner_ids': [(4, self.partner_id.id)],
            },
        }

    def action_view_meetings(self):
        """Con una sola reunión, abre su formulario directo como
        diálogo (una sola vista, funciona bien). Con varias, navega a
        la vista de calendario/lista clásica en vez de forzar un
        diálogo multi-vista -mismo criterio que ya usa
        chatroom_sales_intelligence para Ventas/Compras/WhatsApp."""
        self.ensure_one()
        if not self.partner_id:
            raise UserError(_("Esta conversación no tiene un contacto asociado."))
        meetings = self._get_meetings()
        if not meetings:
            raise UserError(_(
                "%s todavía no tiene ninguna reunión agendada.") % self.partner_id.name)
        if len(meetings) == 1:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'calendar.event',
                'res_id': meetings.id,
                'views': [(False, 'form')],
                'target': 'new',
            }
        return {
            'type': 'ir.actions.act_window',
            'name': _("Reuniones"),
            'res_model': 'calendar.event',
            'views': [(False, 'calendar'), (False, 'list'), (False, 'form')],
            'domain': [('partner_ids', 'in', self.partner_id.id)],
        }

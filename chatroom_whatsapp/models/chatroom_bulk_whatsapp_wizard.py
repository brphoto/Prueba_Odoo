# -*- coding: utf-8 -*-
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError

DIGITS_RE = re.compile(r'\D')


class ChatroomBulkWhatsappWizard(models.TransientModel):
    """Enviar una plantilla de WhatsApp a varios contactos de una: se
    abre desde el menú de Acciones de cualquier lista con un partner
    resoluble (Contactos, Oportunidades, Presupuestos/Pedidos,
    Facturas), sobre los registros seleccionados."""
    _name = 'chatroom.bulk.whatsapp.wizard'
    _description = "Envío masivo de WhatsApp"

    template_id = fields.Many2one(
        'chatroom.template', required=True, string="Plantilla",
        domain=[('status', '=', 'approved')],
        help="Solo plantillas aprobadas por Meta: un envío masivo "
             "prácticamente siempre le llega a alguien fuera de la "
             "ventana de 24h, así que un mensaje de texto libre "
             "quedaría rechazado.")
    recipient_count = fields.Integer(compute='_compute_recipient_count')
    eligible_recipient_count = fields.Integer(compute='_compute_recipient_count')
    opt_out_count = fields.Integer(compute='_compute_recipient_count')
    preview = fields.Text(compute='_compute_preview')
    readiness_message = fields.Char(compute='_compute_readiness')
    ready_to_queue = fields.Boolean(compute='_compute_readiness')

    @api.depends('template_id', 'recipient_count', 'eligible_recipient_count', 'opt_out_count')
    def _compute_preview(self):
        for wizard in self:
            if wizard.template_id:
                wizard.preview = _('%s apto(s) recibirán la plantilla "%s". %s dado(s) de baja se omitirán.') % (
                    wizard.eligible_recipient_count, wizard.template_id.display_name,
                    wizard.opt_out_count)
            else:
                wizard.preview = _('Selecciona una plantilla aprobada para ver el resumen.')

    @api.depends('template_id', 'recipient_count', 'eligible_recipient_count', 'opt_out_count')
    def _compute_readiness(self):
        for wizard in self:
            wizard.ready_to_queue = bool(
                wizard.template_id and wizard.template_id.status == 'approved' and wizard.eligible_recipient_count)
            if not wizard.template_id:
                wizard.readiness_message = _('Selecciona una plantilla aprobada.')
            elif wizard.template_id.status != 'approved':
                wizard.readiness_message = _('La plantilla debe estar aprobada por Meta.')
            elif not wizard.recipient_count:
                wizard.readiness_message = _('No hay contactos con un número de WhatsApp válido.')
            elif not wizard.eligible_recipient_count:
                wizard.readiness_message = _('Todos los contactos válidos están dados de baja.')
            else:
                wizard.readiness_message = _('Listo: el envío se encolará y no bloqueará la pantalla.')

    def _get_target_partners(self):
        """Resuelve un res.partner por cada registro seleccionado
        (active_model/active_ids del contexto) y deduplica por número
        de WhatsApp -no por id de contacto: dos fichas distintas
        podrían compartir el mismo teléfono (ej. varios contactos de
        una misma empresa cargados con el celular del dueño)."""
        active_model = self.env.context.get('active_model')
        active_ids = self.env.context.get('active_ids') or []
        if not active_model or not active_ids:
            return self.env['res.partner']
        records = self.env[active_model].browse(active_ids)
        if active_model == 'res.partner':
            partners = records
        elif 'partner_id' in records._fields:
            partners = records.mapped('partner_id')
        else:
            raise UserError(_(
                "No se puede resolver un contacto para el modelo %s.") % active_model)

        seen_numbers = set()
        unique_partners = self.env['res.partner']
        for partner in partners:
            if not partner or not partner.exists():
                continue
            digits = DIGITS_RE.sub('', partner.whatsapp_id or partner.phone or '')
            if len(digits) < 8:
                continue
            key = digits[-8:]
            if key in seen_numbers:
                continue
            seen_numbers.add(key)
            unique_partners |= partner
        return unique_partners

    @api.depends_context('active_model', 'active_ids')
    def _compute_recipient_count(self):
        for wizard in self:
            partners = wizard._get_target_partners()
            wizard.recipient_count = len(partners)
            wizard.opt_out_count = len(partners.filtered('whatsapp_opt_out'))
            wizard.eligible_recipient_count = len(partners) - wizard.opt_out_count

    def action_send(self):
        """Encola un chatroom.scheduled.message por contacto en vez de
        llamar a la Cloud API de Meta una por una en este mismo request:
        con selecciones grandes eso significaba mantener colgado el
        worker web (y arriesgar timeout del navegador/proxy) hasta
        terminar de mandarle a todo el mundo. El cron que ya procesa los
        mensajes programados (_cron_send_scheduled_messages) se encarga
        del envío real, de a lotes de 100."""
        self.ensure_one()
        if not self.template_id or self.template_id.status != 'approved':
            raise UserError(_("Solo puedes enviar una plantilla aprobada por Meta."))
        partners = self._get_target_partners()
        if not partners:
            raise UserError(_(
                "No hay ningún contacto con un número de WhatsApp válido "
                "en la selección."))

        Channel = self.env['chatroom.channel']
        ScheduledMessage = self.env['chatroom.scheduled.message']
        queued = 0
        skipped = []
        now = fields.Datetime.now()
        for partner in partners:
            if partner.whatsapp_opt_out:
                skipped.append(_("%s (dado de baja)") % partner.name)
                continue
            try:
                channel_id = Channel.action_start_conversation(partner.id)
            except UserError as exc:
                skipped.append(_("%(name)s: %(error)s") % {
                    'name': partner.name, 'error': exc})
                continue
            ScheduledMessage.create({
                'channel_id': channel_id,
                'message_type': 'template',
                'template_id': self.template_id.id,
                'scheduled_date': now,
            })
            queued += 1

        message = _("Se encolaron %s mensajes para mandar en los próximos minutos.") % queued
        if skipped:
            message += " " + _(
                "Se omitieron %(count)s: %(detail)s"
            ) % {'count': len(skipped), 'detail': '; '.join(skipped[:10])}
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Envío masivo de WhatsApp"),
                'message': message,
                'type': 'success' if queued else 'warning',
                'sticky': bool(skipped),
            },
        }

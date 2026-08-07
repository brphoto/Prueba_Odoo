# -*- coding: utf-8 -*-
import base64
import json
import logging
import mimetypes
import re
from datetime import timedelta

import pytz
import requests

from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError
from odoo.http import request

_logger = logging.getLogger(__name__)

# Para la vista previa del último mensaje en el kanban/lista/sidebar de la
# app cuando no tiene texto (una foto sin pie de foto, por ejemplo): sin
# esto se veía en blanco, como si no hubiera pasado nada.
MESSAGE_TYPE_PREVIEW = {
    'image': "📷 Foto",
    'audio': "🎤 Audio",
    'video': "🎥 Video",
    'document': "📄 Documento",
    'template': "📋 Plantilla",
    'other': "📎 Adjunto",
}

# Umbral de SLA de primera respuesta: minutos desde el primer mensaje del
# cliente hasta la primera respuesta de un agente en esa conversación.
SLA_FIRST_RESPONSE_YELLOW_MINUTES = 10
SLA_FIRST_RESPONSE_RED_MINUTES = 15


class ChatroomChannel(models.Model):
    """Una conversación (WhatsApp / Messenger / Instagram) con un contacto.

    Cada canal agrupa los mensajes intercambiados con un mismo número/ID de
    red social, de forma análoga a una bandeja de entrada tipo "chatroom".
    """
    _name = 'chatroom.channel'
    _description = "Conversación de Chatroom (WhatsApp / Redes Sociales)"
    # mail.activity.mixin conecta la conversación gratis con el sistema de
    # Actividades de Odoo (llamadas, reuniones, to-dos con fecha): aparecen
    # en el menú de Actividades de cada usuario y, si son de tipo reunión,
    # también en Calendario. Ningún código propio necesario más allá del
    # mixin: el chatter ya sabe pintar el botón "Programar actividad".
    _inherit = ['mail.thread', 'mail.activity.mixin', 'chatroom.meta.mixin']
    _order = 'last_message_date desc'
    _rec_name = 'display_name'

    display_name = fields.Char(compute='_compute_display_name', store=True)
    channel_type = fields.Selection(
        [('whatsapp', "WhatsApp"),
         ('messenger', "Messenger"),
         ('instagram', "Instagram Direct")],
        default='whatsapp', required=True, tracking=True)
    partner_id = fields.Many2one(
        'res.partner', string="Contacto", tracking=True)
    whatsapp_number_id = fields.Many2one(
        'chatroom.whatsapp.number', string="Línea de WhatsApp", index=True,
        help="Número de WhatsApp Business por el que entró esta "
             "conversación, cuando hay varias líneas configuradas "
             "(ej. Ventas, Soporte). Vacío si solo se usa el número "
             "único configurado en Ajustes.")
    external_id = fields.Char(
        string="ID externo (wa_id / PSID)", required=True, index=True,
        help="Identificador que asigna Meta al usuario final: número de "
             "WhatsApp (wa_id) o Page-Scoped ID (Messenger/Instagram)")
    state = fields.Selection(
        [('open', "Abierta"),
         ('pending', "Pendiente"),
         ('closed', "Cerrada")],
        default='open', tracking=True)
    assigned_user_id = fields.Many2one(
        'res.users', string="Agente asignado", tracking=True,
        default=lambda self: self.env.user)
    assigned_user_initials = fields.Char(compute='_compute_assignment_visual')
    assigned_user_color = fields.Char(compute='_compute_assignment_visual')
    message_ids = fields.One2many(
        'chatroom.message', 'channel_id', string="Mensajes")
    message_count = fields.Integer(compute='_compute_message_stats', store=True)
    unread_count = fields.Integer(compute='_compute_message_stats', store=True)
    last_message_date = fields.Datetime(index=True)
    last_message_preview = fields.Char(compute='_compute_message_stats', store=True)
    ai_suggested_reply = fields.Text(string="Sugerencia de IA")
    ai_summary = fields.Text(string="Resumen de IA")
    ai_intent = fields.Selection(
        [('consulta', "Consulta"),
         ('venta', "Venta"),
         ('soporte', "Soporte"),
         ('queja', "Queja"),
         ('otro', "Otro")],
        string="Intención (IA)", tracking=True)
    company_id = fields.Many2one(
        'res.company', default=lambda self: self.env.company)
    tag_ids = fields.Many2many(
        'chatroom.tag', 'chatroom_channel_tag_rel', 'channel_id', 'tag_id',
        string="Etiquetas")
    last_away_message_date = fields.Datetime(
        copy=False,
        help="Última vez que se mandó el aviso automático de 'fuera de "
             "horario' en esta conversación. Se usa para no repetirlo en "
             "cada mensaje que manda el cliente de madrugada.")
    ai_paused = fields.Boolean(
        string="IA pausada", copy=False,
        help="Si está activo, las automatizaciones de IA no responden "
             "solas en esta conversación aunque estén prendidas en "
             "Ajustes: la está atendiendo un agente humano. Se activa "
             "solo en cuanto un agente manda un mensaje real, y también "
             "se puede prender/apagar a mano desde el encabezado del "
             "chat.")
    cart_line_ids = fields.One2many(
        'chatroom.cart.line', 'channel_id', string="Carrito (IA)")
    cart_total = fields.Float(compute='_compute_cart_total')
    pending_response_minutes = fields.Integer(
        compute='_compute_first_response_sla', string="Minutos esperando 1ra respuesta")
    first_response_sla_state = fields.Selection(
        [('none', "Sin mensajes del cliente"),
         ('green', "A tiempo"),
         ('yellow', "Por vencer"),
         ('red', "Vencido")],
        compute='_compute_first_response_sla', string="SLA 1ra respuesta")
    next_activity_id = fields.Integer(compute='_compute_next_activity')
    next_activity_summary = fields.Char(compute='_compute_next_activity')
    next_activity_date_deadline = fields.Date(compute='_compute_next_activity')
    next_activity_overdue = fields.Boolean(compute='_compute_next_activity')
    next_activity_user_id = fields.Many2one(
        'res.users', compute='_compute_next_activity')
    sla_breach_notified = fields.Boolean(
        default=False, copy=False,
        help="Ya se le avisó al agente asignado que esta conversación "
             "está en rojo de SLA; evita mandarle el mismo aviso en cada "
             "corrida del cron. Se reinicia solo en cuanto un agente "
             "responde o llega una conversación nueva.")
    csat_score = fields.Integer(string="Calificación del cliente (1-5)", copy=False)
    csat_requested = fields.Boolean(
        default=False, copy=False,
        help="Hay una encuesta de satisfacción mandada esperando "
             "respuesta del cliente.")
    csat_answered_at = fields.Datetime(copy=False)

    @api.depends('cart_line_ids.quantity', 'cart_line_ids.price_unit')
    def _compute_cart_total(self):
        for rec in self:
            rec.cart_total = sum(line.quantity * line.price_unit for line in rec.cart_line_ids)

    @api.depends('assigned_user_id')
    def _compute_assignment_visual(self):
        palette = ('#3b82f6', '#16a34a', '#f59e0b', '#8b5cf6', '#ef4444', '#0891b2')
        for rec in self:
            user = rec.assigned_user_id
            if not user:
                rec.assigned_user_initials = ''
                rec.assigned_user_color = '#94a3b8'
                continue
            words = (user.name or '').split()
            rec.assigned_user_initials = ''.join(word[0] for word in words[:2]).upper()
            rec.assigned_user_color = palette[(user.color or user.id) % len(palette)]

    def _sla_settings(self):
        icp = self.env['ir.config_parameter'].sudo()
        enabled = icp.get_param('chatroom_whatsapp.sla_enabled', 'True') != 'False'
        try:
            yellow = int(icp.get_param(
                'chatroom_whatsapp.sla_yellow_minutes', SLA_FIRST_RESPONSE_YELLOW_MINUTES))
        except (TypeError, ValueError):
            yellow = SLA_FIRST_RESPONSE_YELLOW_MINUTES
        try:
            red = int(icp.get_param(
                'chatroom_whatsapp.sla_red_minutes', SLA_FIRST_RESPONSE_RED_MINUTES))
        except (TypeError, ValueError):
            red = SLA_FIRST_RESPONSE_RED_MINUTES
        return enabled, max(1, yellow), max(yellow + 1, red)

    @api.depends('message_ids.direction', 'message_ids.date')
    def _compute_first_response_sla(self):
        """Semáforo en vivo (no está 'store', a diferencia del campo
        'first_response_minutes' que ya existe para promediar tiempos de
        respuesta en las métricas): mientras no haya respuesta saliente
        cuenta los minutos que lleva esperando el cliente, para poder
        avisar de un SLA vencido incluso sin que nadie haya respondido
        todavía (algo que un campo calculado solo al responder no puede
        mostrar)."""
        enabled, yellow_limit, red_limit = self._sla_settings()
        now = fields.Datetime.now()
        for rec in self:
            first_inbound = rec.message_ids.filtered(lambda m: m.direction == 'inbound').sorted('date')[:1]
            if not first_inbound:
                rec.pending_response_minutes = 0
                rec.first_response_sla_state = 'none'
                continue
            first_inbound_date = first_inbound.date
            first_outbound = rec.message_ids.filtered(
                lambda m: m.direction == 'outbound' and m.date >= first_inbound_date
            ).sorted('date')[:1]
            if first_outbound:
                rec.pending_response_minutes = 0
                rec.first_response_sla_state = 'green'
                continue
            minutes = int((now - first_inbound_date).total_seconds() / 60)
            rec.pending_response_minutes = minutes
            if not enabled:
                rec.first_response_sla_state = 'none'
            elif minutes < yellow_limit:
                rec.first_response_sla_state = 'green'
            elif minutes < red_limit:
                rec.first_response_sla_state = 'yellow'
            else:
                rec.first_response_sla_state = 'red'

    @api.model
    def _cron_notify_sla_breach(self):
        """Avisa una sola vez por conversación cuando se vence el SLA de
        primera respuesta (rojo), igual que el aviso de oportunidades
        estancadas en crm_customer_intelligence: se manda como
        notificación (message_type='notification' por defecto) para que
        NO cuente como respuesta y no reinicie el semáforo sola."""
        channels = self.search([('state', 'in', ('open', 'pending'))])
        for channel in channels:
            if channel.first_response_sla_state == 'red':
                if not channel.sla_breach_notified and channel.assigned_user_id:
                    channel.message_post(
                        body=_(
                            "⏱️ Esta conversación lleva %(minutes)s minutos "
                            "sin primera respuesta (SLA vencido). Contactá "
                            "a %(contact)s."
                        ) % {
                            'minutes': channel.pending_response_minutes,
                            'contact': channel.partner_id.name or channel.external_id,
                        },
                        partner_ids=[channel.assigned_user_id.partner_id.id],
                        subtype_xmlid='mail.mt_comment',
                    )
                    channel.sla_breach_notified = True
            elif channel.sla_breach_notified:
                channel.sla_breach_notified = False

    @api.model
    def _cron_process_assignment_sla(self):
        """Libera y vuelve a repartir conversaciones sin primera respuesta.

        La regla es configurable desde Ajustes. Solo se ejecuta una vez que
        el SLA está rojo y nunca cambia el historial de mensajes: registra la
        reasignación en chatroom.assignment.log y notifica al nuevo agente.
        """
        icp = self.env['ir.config_parameter'].sudo()
        enabled = icp.get_param('chatroom_whatsapp.sla_enabled', 'True') != 'False'
        auto_reassign = icp.get_param(
            'chatroom_whatsapp.sla_auto_reassign', 'True') != 'False'
        auto_assign = icp.get_param(
            'chatroom_whatsapp.auto_assign', 'True') != 'False'
        if not enabled or not auto_reassign or not auto_assign:
            return
        agents = self._get_default_agents()
        if not agents:
            return
        for channel in self.search([('state', 'in', ('open', 'pending'))]):
            if channel.first_response_sla_state != 'red' or not channel.assigned_user_id:
                continue
            candidates = agents - channel.assigned_user_id
            if not candidates:
                candidates = agents
            next_agent = self._get_next_assignee(candidates)
            if next_agent == channel.assigned_user_id:
                continue
            channel.with_context(chatroom_assignment_reason='sla').write({
                'assigned_user_id': next_agent.id if next_agent else False,
            })

    # No es un Many2one a 'crm.lead': CRM es un módulo opcional (no está
    # en 'depends'), y un campo relacional a un modelo no instalado rompe
    # la carga del registro. Se guarda el id "a mano" y se resuelve solo
    # si CRM está instalado (ver _compute_related_counts).
    pinned_lead_id = fields.Integer(string="ID de oportunidad vinculada", copy=False)
    pinned_lead_name = fields.Char(compute='_compute_related_counts')
    crm_installed = fields.Boolean(compute='_compute_related_counts')
    calendar_installed = fields.Boolean(compute='_compute_related_counts')
    sale_installed = fields.Boolean(compute='_compute_related_counts')
    purchase_installed = fields.Boolean(compute='_compute_related_counts')
    account_installed = fields.Boolean(compute='_compute_related_counts')
    project_installed = fields.Boolean(compute='_compute_related_counts')
    lead_count = fields.Integer(compute='_compute_related_counts')
    sale_order_count = fields.Integer(compute='_compute_related_counts')
    purchase_order_count = fields.Integer(compute='_compute_related_counts')
    invoice_count = fields.Integer(compute='_compute_related_counts')
    task_count = fields.Integer(compute='_compute_related_counts')

    window_expires_at = fields.Datetime(compute='_compute_session_window')
    is_session_open = fields.Boolean(
        compute='_compute_session_window',
        help="La API de WhatsApp solo permite mensajes de texto libres "
             "durante las 24h siguientes al último mensaje del cliente. "
             "Fuera de esa ventana hay que usar una plantilla aprobada.")

    first_response_minutes = fields.Float(
        string="Primera respuesta (min)", compute='_compute_first_response_minutes', store=True,
        help="Minutos entre el primer mensaje del cliente y la primera "
             "respuesta saliente de un agente.")

    _external_id_type_uniq = models.Constraint(
        'unique(external_id, channel_type, company_id)',
        "Ya existe una conversación abierta para este contacto en este canal.",
    )

    @api.depends('partner_id', 'external_id', 'channel_type')
    def _compute_display_name(self):
        for rec in self:
            name = rec.partner_id.name or rec.external_id or _("Nuevo contacto")
            rec.display_name = f"{name} ({dict(rec._fields['channel_type'].selection).get(rec.channel_type)})"

    @api.depends('message_ids.state', 'message_ids.direction', 'message_ids.body')
    def _compute_message_stats(self):
        for rec in self:
            messages = rec.message_ids
            rec.message_count = len(messages)
            rec.unread_count = len(messages.filtered(
                lambda m: m.direction == 'inbound' and m.state != 'read'))
            last = messages.sorted('date', reverse=True)[:1]
            if last:
                preview = last.body or MESSAGE_TYPE_PREVIEW.get(last.message_type, '')
                rec.last_message_preview = preview[:120]
            else:
                rec.last_message_preview = ''

    def _compute_related_counts(self):
        crm_installed = 'crm.lead' in self.env
        calendar_installed = 'calendar.event' in self.env
        sale_installed = 'sale.order' in self.env
        purchase_installed = 'purchase.order' in self.env
        account_installed = 'account.move' in self.env
        project_installed = 'project.task' in self.env
        pinned_leads = {}
        if crm_installed:
            pinned_ids = [rec.pinned_lead_id for rec in self if rec.pinned_lead_id]
            if pinned_ids:
                pinned_leads = {
                    lead.id: lead.display_name
                    for lead in self.env['crm.lead'].browse(pinned_ids).exists()
                }
        for rec in self:
            rec.crm_installed = crm_installed
            rec.calendar_installed = calendar_installed
            rec.sale_installed = sale_installed
            rec.purchase_installed = purchase_installed
            rec.account_installed = account_installed
            rec.project_installed = project_installed
            rec.pinned_lead_name = pinned_leads.get(rec.pinned_lead_id, False)
            partner = rec.partner_id
            rec.lead_count = (
                self.env['crm.lead'].search_count([('partner_id', '=', partner.id)])
                if crm_installed and partner else 0)
            rec.sale_order_count = (
                self.env['sale.order'].search_count([('partner_id', '=', partner.id)])
                if sale_installed and partner else 0)
            rec.purchase_order_count = (
                self.env['purchase.order'].search_count([('partner_id', '=', partner.id)])
                if purchase_installed and partner else 0)
            rec.invoice_count = (
                self.env['account.move'].search_count([
                    ('partner_id', '=', partner.id),
                    ('move_type', 'in', ('out_invoice', 'out_refund')),
                ]) if account_installed and partner else 0)
            rec.task_count = (
                self.env['project.task'].search_count([('partner_id', '=', partner.id)])
                if project_installed and partner else 0)

    def _compute_session_window(self):
        now = fields.Datetime.now()
        for rec in self:
            last_inbound = rec.message_ids.filtered(
                lambda m: m.direction == 'inbound').sorted('date', reverse=True)[:1]
            if last_inbound:
                rec.window_expires_at = fields.Datetime.add(last_inbound.date, hours=24)
                rec.is_session_open = now < rec.window_expires_at
            else:
                rec.window_expires_at = False
                rec.is_session_open = False

    @api.depends('message_ids.direction', 'message_ids.date')
    def _compute_first_response_minutes(self):
        for rec in self:
            messages = rec.message_ids.sorted('date')
            first_inbound = next((m for m in messages if m.direction == 'inbound'), None)
            first_outbound = next((
                m for m in messages
                if m.direction == 'outbound' and (not first_inbound or m.date > first_inbound.date)
            ), None) if first_inbound else None
            if first_inbound and first_outbound:
                delta = first_outbound.date - first_inbound.date
                rec.first_response_minutes = round(delta.total_seconds() / 60.0, 2)
            else:
                rec.first_response_minutes = 0.0

    # ------------------------------------------------------------------
    # Helpers de contacto / canal
    # ------------------------------------------------------------------
    @api.model
    def _find_or_create_from_webhook(self, channel_type, external_id, profile_name=None,
                                      meta_phone_number_id=None):
        """Busca el canal para un contacto; crea el res.partner y el canal
        si es la primera vez que escribe (creación automática de contactos).

        :param meta_phone_number_id: 'phone_number_id' que viene en
            `value.metadata` del webhook de WhatsApp, para asociar la
            conversación a la línea correcta cuando hay varias.
        """
        channel = self.search([
            ('channel_type', '=', channel_type),
            ('external_id', '=', external_id),
        ], limit=1)
        if channel:
            return channel

        partner = self.env['res.partner'].search(
            [('whatsapp_id', '=', external_id)], limit=1)
        if not partner and channel_type == 'whatsapp':
            # external_id es un número de verdad solo en WhatsApp (en
            # Messenger/Instagram es un PSID, no comparable por teléfono).
            partner = self.env['res.partner']._find_by_whatsapp_number(external_id)
            if partner:
                partner.whatsapp_id = external_id
        if not partner:
            partner = self.env['res.partner'].create({
                'name': profile_name or external_id,
                'whatsapp_id': external_id,
                'phone': f"+{external_id}" if channel_type == 'whatsapp' else False,
            })

        whatsapp_number = self.env['chatroom.whatsapp.number']._find_by_phone_number_id(
            meta_phone_number_id)
        assignee = whatsapp_number._get_next_assignee() if whatsapp_number else self._get_next_assignee()

        return self.create({
            'channel_type': channel_type,
            'external_id': external_id,
            'partner_id': partner.id,
            'whatsapp_number_id': whatsapp_number.id if whatsapp_number else False,
            'assigned_user_id': assignee.id,
        })

    @api.model
    def action_start_conversation(self, partner_id, phone=False, whatsapp_number_id=False):
        """Inicia una conversación **por nosotros** (seguimiento, encuesta,
        aviso...), en vez de esperar a que el cliente escriba primero.

        Encuentra o crea el canal de WhatsApp del contacto y lo asigna al
        agente actual. No envía nada: como es una conversación nueva, casi
        siempre va a estar fuera de la ventana de 24h (`is_session_open`
        en False), así que la propia interfaz de chat va a pedir usar una
        plantilla para el primer mensaje — igual que WhatsApp exige.

        :param phone: si no se pasa, se usa el `phone` del contacto.
        :return: id del canal (nuevo o ya existente para ese contacto).
        """
        partner = self.env['res.partner'].browse(partner_id)
        if not partner.exists():
            raise UserError(_("El contacto ya no existe."))

        digits = re.sub(r'\D', '', phone or partner.phone or '')
        if len(digits) < 8:
            raise UserError(_(
                "Necesito un número de WhatsApp válido (con código de "
                "país) para %s.") % partner.name)

        if not partner.whatsapp_id:
            partner.whatsapp_id = digits

        channel = self.search([
            ('channel_type', '=', 'whatsapp'),
            ('external_id', '=', digits),
        ], limit=1)
        if channel:
            if not channel.partner_id:
                channel.partner_id = partner.id
            return channel.id

        whatsapp_number = self.env['chatroom.whatsapp.number'].browse(whatsapp_number_id) \
            if whatsapp_number_id else self.env['chatroom.whatsapp.number']
        channel = self.create({
            'channel_type': 'whatsapp',
            'external_id': digits,
            'partner_id': partner.id,
            'whatsapp_number_id': whatsapp_number.id if whatsapp_number else False,
            'assigned_user_id': self.env.user.id,
        })
        return channel.id

    @api.model
    def _get_default_agents(self):
        """Todos los agentes del grupo 'Chatroom / Agente' + 'Chatroom /
        Administrador'. No basta con leer solo 'Agente': pertenecer a
        'Administrador' no vuelve a alguien miembro explícito del grupo
        que implica ('user_ids' no incluye la membresía heredada), así
        que se unen ambos para no dejar afuera a los managers."""
        return (
            self.env.ref('chatroom_whatsapp.group_chatroom_user').user_ids
            | self.env.ref('chatroom_whatsapp.group_chatroom_manager').user_ids
        )

    def _notify_assignment_change(self, reason='manual'):
        self.ensure_one()
        if not self.assigned_user_id or not self.assigned_user_id.partner_id:
            return
        if reason == 'sla':
            body = _(
                "La conversación de %(contact)s fue liberada por vencimiento "
                "del SLA y reasignada a %(agent)s.") % {
                    'contact': self.display_name,
                    'agent': self.assigned_user_id.name,
                }
        else:
            body = _(
                "La conversación de %(contact)s fue asignada a %(agent)s.") % {
                    'contact': self.display_name,
                    'agent': self.assigned_user_id.name,
                }
        self.message_post(
            body=body,
            partner_ids=[self.assigned_user_id.partner_id.id],
            subtype_xmlid='mail.mt_comment',
        )

    def action_quick_reassign(self, user_id=False):
        self.ensure_one()
        user = self.env['res.users'].browse(user_id).exists()
        if not user or user not in self._get_default_agents():
            raise UserError(_("El usuario elegido no es un agente válido de Chatroom."))
        self.write({'assigned_user_id': user.id})
        return {
            'assigned_user_id': user.id,
            'assigned_user_name': user.name,
            'assigned_user_initials': self.assigned_user_initials,
            'assigned_user_color': self.assigned_user_color,
        }

    def get_assignment_history(self, limit=20):
        self.ensure_one()
        logs = self.env['chatroom.assignment.log'].sudo().search(
            [('channel_id', '=', self.id)], order='changed_at desc, id desc', limit=limit)
        return [{
            'id': log.id,
            'previous_user_name': log.previous_user_id.name or _("Sin asignar"),
            'new_user_name': log.new_user_id.name or _("Sin asignar"),
            'reason': log.reason,
            'note': log.note or '',
            'changed_by_name': log.changed_by.name or _("Sistema"),
            'changed_at': fields.Datetime.to_string(log.changed_at),
        } for log in logs]

    @api.model
    def get_assignable_agents(self):
        """Para el selector de reasignación rápida del chat."""
        palette = ('#3b82f6', '#16a34a', '#f59e0b', '#8b5cf6', '#ef4444', '#0891b2')
        agents = self._get_default_agents().sorted(key=lambda user: user.name or '')
        return [{
            'id': u.id,
            'name': u.name,
            'initials': ''.join(word[0] for word in (u.name or '').split()[:2]).upper(),
            'color': palette[(u.color or u.id) % len(palette)],
        } for u in agents]

    @api.model
    def _get_next_assignee(self, agents=None):
        """Reparte las conversaciones nuevas entre agentes, asignando al
        que menos conversaciones abiertas tenga en este momento (balanceo
        de carga simple).

        :param agents: recordset de res.users a considerar. Si es None,
            se usa el grupo general 'Chatroom / Agente' (+ Administrador).
            Lo pasa `chatroom.whatsapp.number._get_next_assignee()` para
            repartir solo entre los agentes de esa línea.
        """
        icp = self.env['ir.config_parameter'].sudo()
        if icp.get_param('chatroom_whatsapp.auto_assign', 'True') == 'False':
            return self.env.user
        if agents is None:
            agents = self._get_default_agents()
        if not agents:
            return self.env.user
        open_counts = self.env['chatroom.channel']._read_group(
            [('assigned_user_id', 'in', agents.ids), ('state', 'in', ('open', 'pending'))],
            ['assigned_user_id'], ['__count'])
        counts = {user.id: count for user, count in open_counts}
        least_busy = min(agents, key=lambda u: counts.get(u.id, 0))
        return least_busy

    def _notify_assigned_agent(self, message):
        """Avisa al agente asignado por el sistema nativo de notificaciones
        de Odoo (bandeja/campanita de Discuss), sin infraestructura extra."""
        self.ensure_one()
        if not self.assigned_user_id or not self.assigned_user_id.partner_id:
            return
        self.message_post(
            body=_("Nuevo mensaje de %(who)s: %(body)s") % {
                'who': self.partner_id.name or self.external_id,
                'body': (message.body or _("(adjunto)"))[:140],
            },
            partner_ids=[self.assigned_user_id.partner_id.id],
            subtype_xmlid='mail.mt_comment',
        )

    # ------------------------------------------------------------------
    # Notas internas: se ven mezcladas con las burbujas del chat (con
    # otro estilo, para no confundirlas con mensajes reales al cliente)
    # pero viven en el chatter de siempre (mail.message, subtipo "nota"),
    # no en chatroom.message — nunca pueden confundirse con algo que
    # salió de verdad por WhatsApp.
    # ------------------------------------------------------------------
    def action_post_internal_note(self, body):
        self.ensure_one()
        if not (body or '').strip():
            raise UserError(_("Escribe algo para la nota."))
        mentioned_partners = []
        mentioned_names = {
            name.lower().replace('_', ' ')
            for name in re.findall(r'@([^\s@]+)', body or '')
        }
        for agent in self._get_default_agents():
            normalized = (agent.name or '').lower()
            compact = normalized.replace(' ', '_')
            if normalized in mentioned_names or compact in {
                    name.replace(' ', '_') for name in mentioned_names}:
                if agent.partner_id:
                    mentioned_partners.append(agent.partner_id.id)
        self.message_post(
            body=body,
            partner_ids=mentioned_partners,
            subtype_xmlid='mail.mt_note',
        )
        self._notify_thread_update()
        return True

    def get_internal_notes(self):
        self.ensure_one()
        note_subtype = self.env.ref('mail.mt_note', raise_if_not_found=False)
        domain = [
            ('model', '=', 'chatroom.channel'),
            ('res_id', '=', self.id),
            ('message_type', '=', 'comment'),
        ]
        if note_subtype:
            domain.append(('subtype_id', '=', note_subtype.id))
        notes = self.env['mail.message'].search(domain, order='date asc')
        return [{
            'id': f'note-{note.id}',
            'body': tools.html2plaintext(note.body) if note.body else '',
            'date': note.date,
            'author_name': note.author_id.name or _("Sistema"),
        } for note in notes]

    def write(self, vals):
        previous_assignees = {rec.id: rec.assigned_user_id for rec in self} if 'assigned_user_id' in vals else {}
        previous_numbers = {rec.id: rec.whatsapp_number_id for rec in self} if 'whatsapp_number_id' in vals else {}
        res = super().write(vals)
        if 'assigned_user_id' in vals:
            reason = self.env.context.get('chatroom_assignment_reason', 'manual')
            for rec in self:
                previous_user = previous_assignees.get(rec.id)
                previous_id = previous_user.id if previous_user else False
                current_id = rec.assigned_user_id.id
                if current_id == previous_id:
                    continue
                self.env['chatroom.assignment.log'].sudo().create({
                    'channel_id': rec.id,
                    'previous_user_id': previous_id or False,
                    'new_user_id': current_id or False,
                    'reason': reason,
                    'note': "SLA vencido" if reason == 'sla' else False,
                })
            for rec in self:
                if rec.assigned_user_id and rec.assigned_user_id != previous_assignees.get(rec.id) \
                        and rec.assigned_user_id.partner_id:
                    rec.message_post(
                        body=_("Te asignaron la conversación de %s.") % (
                            rec.partner_id.name or rec.external_id),
                        partner_ids=[rec.assigned_user_id.partner_id.id],
                        subtype_xmlid='mail.mt_comment',
                    )
        if 'whatsapp_number_id' in vals:
            # Transferir de línea/equipo: se resuelve con el mismo campo de
            # siempre (no hay una acción/wizard aparte), pero acá se deja
            # rastro en las notas internas y, si no se pidió también un
            # agente puntual en el mismo write, se reparte entre el equipo
            # de la línea nueva en vez de dejarla en el agente de la línea
            # vieja (que puede no pertenecer al equipo nuevo).
            for rec in self:
                old_number = previous_numbers.get(rec.id)
                if rec.whatsapp_number_id == old_number:
                    continue
                rec.message_post(
                    body=_("Conversación transferida de %(old)s a %(new)s.") % {
                        'old': old_number.name if old_number else _("sin línea"),
                        'new': rec.whatsapp_number_id.name if rec.whatsapp_number_id else _("sin línea"),
                    },
                    subtype_xmlid='mail.mt_note',
                )
                if 'assigned_user_id' not in vals and rec.whatsapp_number_id:
                    next_agent = rec.whatsapp_number_id._get_next_assignee()
                    if next_agent:
                        rec.assigned_user_id = next_agent.id
        return res

    # ------------------------------------------------------------------
    # Cumplimiento: opt-out / consentimiento
    # ------------------------------------------------------------------
    def _check_can_send(self):
        self.ensure_one()
        if self.partner_id and self.partner_id.whatsapp_opt_out:
            raise UserError(_(
                "%s se dio de baja de los mensajes de este número; no se "
                "le pueden enviar mensajes hasta que vuelva a escribir la "
                "palabra clave de alta.") % self.partner_id.name)
        # Todo lo que manda esta conversación pasa por acá (texto,
        # adjuntos, reacciones, reintentos, plantillas, botones): es el
        # único lugar donde se puede distinguir "un agente de verdad
        # tocó Enviar" de "lo mandó la automatización" sin agregar un
        # flag manual en cada llamada. Dos automatizaciones disparan
        # sends sin que haya una persona atendiendo:
        #   - el webhook (auth='public'): corre como el usuario público,
        #     así que _is_public() alcanza para descartarlo.
        #   - los cron (reintentos, mensajes programados): NO corren
        #     dentro de un http.request, a diferencia de un clic real en
        #     el webclient (que sí pasa por /web/dataset/call_kw) aunque
        #     el usuario del cron sea un administrador con permisos de
        #     persona real. Por eso hace falta el chequeo de `request`
        #     además de `_is_public()`; solo con `_is_public()` un mensaje
        #     programado o un reintento automático pausaban la IA solos.
        if not self.ai_paused and request and not self.env.user._is_public():
            self.ai_paused = True
            self.message_post(
                body=_("IA pausada automáticamente: %s tomó la conversación.")
                % self.env.user.name,
                subtype_xmlid='mail.mt_note',
            )

    def action_toggle_ai_paused(self):
        self.ensure_one()
        self.ai_paused = not self.ai_paused
        self.message_post(
            body=_("IA %s por %s.") % (
                _("pausada") if self.ai_paused else _("reactivada"), self.env.user.name),
            subtype_xmlid='mail.mt_note',
        )
        return self.ai_paused

    def _handle_opt_keywords(self, message):
        """Detecta palabras clave de baja/alta en un mensaje entrante
        (ej. 'STOP', 'BAJA', 'INICIAR') y actualiza el consentimiento del
        contacto. Evita mandar mensajes a quien pidió no recibir más,
        que es la causa más común de que Meta bloquee un número."""
        self.ensure_one()
        if not self.partner_id or not message.body:
            return
        icp = self.env['ir.config_parameter'].sudo()
        stop_words = {
            w.strip().lower() for w in icp.get_param(
                'chatroom_whatsapp.opt_out_keywords', 'stop,baja,cancelar,unsubscribe'
            ).split(',') if w.strip()
        }
        start_words = {
            w.strip().lower() for w in icp.get_param(
                'chatroom_whatsapp.opt_in_keywords', 'iniciar,start,alta'
            ).split(',') if w.strip()
        }
        text = message.body.strip().lower()

        if text in stop_words and not self.partner_id.whatsapp_opt_out:
            try:
                self.action_send_text(_(
                    "Has cancelado tu suscripción a los mensajes de este "
                    "número. Escribe INICIAR si quieres volver a recibirlos."))
            except UserError as exc:
                _logger.warning("No se pudo confirmar la baja en canal %s: %s", self.id, exc)
            self.partner_id.write({
                'whatsapp_opt_out': True,
                'whatsapp_opt_out_date': fields.Datetime.now(),
            })
        elif text in start_words and self.partner_id.whatsapp_opt_out:
            self.partner_id.write({'whatsapp_opt_out': False, 'whatsapp_opt_out_date': False})
            try:
                self.action_send_text(_("Listo, has vuelto a activar los mensajes de este número."))
            except UserError as exc:
                _logger.warning("No se pudo confirmar el alta en canal %s: %s", self.id, exc)

    # ------------------------------------------------------------------
    # Horario de atención: aviso automático fuera de horas, para no dejar
    # a alguien esperando toda la noche sin saber que nadie va a
    # contestar hasta la mañana siguiente.
    # ------------------------------------------------------------------
    def _is_within_business_hours(self, dt=None):
        """True si el horario de atención está desactivado (no hay
        restricción) o si `dt` (o ahora) cae dentro del horario
        configurado en la zona horaria de la empresa."""
        icp = self.env['ir.config_parameter'].sudo()
        if not icp.get_param('chatroom_whatsapp.business_hours_enabled'):
            return True
        # 'res.company' no tiene campo 'tz' propio en Odoo base (lo agrega
        # el módulo 'resource', que este módulo no depende de); se usa el
        # de un parámetro explícito y, si no está, el del usuario actual.
        tz_name = icp.get_param('chatroom_whatsapp.business_hours_tz') \
            or self.env.user.tz or 'UTC'
        try:
            tz = pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            tz = pytz.UTC
        now_utc = dt or fields.Datetime.now()
        local = pytz.UTC.localize(now_utc).astimezone(tz)

        weekdays_param = icp.get_param('chatroom_whatsapp.business_hours_weekdays', '0,1,2,3,4')
        weekdays = {int(d) for d in weekdays_param.split(',') if d.strip().isdigit()}
        if weekdays and local.weekday() not in weekdays:
            return False

        start = float(icp.get_param('chatroom_whatsapp.business_hours_start', '0') or 0)
        end = float(icp.get_param('chatroom_whatsapp.business_hours_end', '24') or 24)
        hour_decimal = local.hour + local.minute / 60.0
        return start <= hour_decimal < end

    def _maybe_send_away_message(self):
        """Si el horario de atención está activo y ahora está fuera de
        hora, manda el aviso automático (una sola vez por día por
        conversación, no en cada mensaje que llegue de madrugada).
        Devuelve True si lo mandó, para que el llamador decida si tiene
        sentido seguir con el resto de las automatizaciones (por ejemplo,
        no tiene mucho sentido que la IA también responda de una)."""
        self.ensure_one()
        icp = self.env['ir.config_parameter'].sudo()
        if not icp.get_param('chatroom_whatsapp.business_hours_enabled'):
            return False
        if self._is_within_business_hours():
            return False
        today = fields.Date.context_today(self)
        if self.last_away_message_date and self.last_away_message_date.date() == today:
            return False
        away_message = icp.get_param('chatroom_whatsapp.business_hours_away_message') or _(
            "Gracias por escribirnos. En este momento estamos fuera de "
            "nuestro horario de atención; te respondemos apenas volvamos.")
        try:
            self.action_send_text(away_message)
        except UserError as exc:
            _logger.warning(
                "No se pudo mandar el aviso de fuera de horario en canal %s: %s", self.id, exc)
            return False
        self.last_away_message_date = fields.Datetime.now()
        return True

    def _get_meta_credentials(self):
        """Si la conversación pertenece a una línea con Phone Number ID
        propio, se usa esa; si no, se cae al número único de Ajustes
        (comportamiento de siempre para instalaciones de un solo número)."""
        self.ensure_one()
        if self.whatsapp_number_id:
            return self.whatsapp_number_id._get_credentials()
        return super()._get_meta_credentials()

    # ------------------------------------------------------------------
    # Envío de mensajes (API directa de Meta, sin proveedores externos)
    # ------------------------------------------------------------------
    def _get_reply_context(self, reply_to_id):
        """Valida y devuelve el mensaje que se quiere citar (respuesta con
        cita, al estilo WhatsApp), o False si no se pidió citar nada.

        Meta solo permite citar mensajes que ya tienen un wa_message_id
        confirmado (el ID que asignó WhatsApp), así que un mensaje fallido
        o una nota interna no se pueden citar.
        """
        self.ensure_one()
        if not reply_to_id:
            return False
        message = self.env['chatroom.message'].browse(reply_to_id)
        if not message.exists() or message.channel_id.id != self.id:
            raise UserError(_("No se puede citar ese mensaje."))
        if not message.wa_message_id:
            raise UserError(_(
                "No se puede citar este mensaje: todavía no tiene un ID "
                "de WhatsApp confirmado (puede estar fallido o pendiente "
                "de enviarse)."))
        return message

    def action_send_text(self, body, reply_to_id=False):
        """Envía un mensaje de texto directo al Graph API de Meta y guarda
        el registro saliente."""
        self.ensure_one()
        self._check_can_send()
        if self.channel_type != 'whatsapp':
            return self._send_meta_page_text(body)

        reply_to = self._get_reply_context(reply_to_id)
        token, phone_number_id, api_version = self._get_meta_credentials()
        url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": self.external_id,
            "type": "text",
            "text": {"body": body},
        }
        if reply_to:
            payload["context"] = {"message_id": reply_to.wa_message_id}
        headers = {"Authorization": f"Bearer {token}"}

        message = self.env['chatroom.message'].create({
            'channel_id': self.id,
            'direction': 'outbound',
            'message_type': 'text',
            'body': body,
            'state': 'sent',
            'date': fields.Datetime.now(),
            'sender_user_id': self.env.user.id,
            'reply_to_id': reply_to.id if reply_to else False,
        })

        try:
            response = self._meta_request('POST', url, json=payload, headers=headers, timeout=15)
            response.raise_for_status()
            data = response.json()
            wa_message_id = data.get('messages', [{}])[0].get('id')
            message.write({'wa_message_id': wa_message_id})
        except requests.RequestException as exc:
            _logger.error("Error enviando mensaje WhatsApp: %s", exc)
            message.write({'state': 'failed'})
            raise UserError(_("No se pudo enviar el mensaje: %s") % exc)

        self.write({
            'last_message_date': fields.Datetime.now(),
            'state': 'open',
        })
        self._notify_thread_update()
        return message

    def _send_meta_page_text(self, body):
        """Envía texto por Messenger/Instagram con el token de Página de
        Meta (distinto del token de WhatsApp: ambos productos usan
        credenciales separadas dentro de la misma App de Meta)."""
        self.ensure_one()
        token, api_version = self._get_meta_page_credentials()
        url = f"https://graph.facebook.com/{api_version}/me/messages"
        payload = {
            "recipient": {"id": self.external_id},
            "message": {"text": body},
            "messaging_type": "RESPONSE",
        }
        headers = {"Authorization": f"Bearer {token}"}

        message = self.env['chatroom.message'].create({
            'channel_id': self.id,
            'direction': 'outbound',
            'message_type': 'text',
            'body': body,
            'state': 'sent',
            'date': fields.Datetime.now(),
            'sender_user_id': self.env.user.id,
        })
        try:
            response = self._meta_request('POST', url, json=payload, headers=headers, timeout=15)
            response.raise_for_status()
            message.write({'wa_message_id': response.json().get('message_id')})
        except requests.RequestException as exc:
            _logger.error("Error enviando mensaje Messenger/Instagram: %s", exc)
            message.write({'state': 'failed'})
            raise UserError(_("No se pudo enviar el mensaje: %s") % exc)

        self.write({'last_message_date': fields.Datetime.now(), 'state': 'open'})
        self._notify_thread_update()
        return message

    @staticmethod
    def _meta_media_type(mimetype):
        mimetype = mimetype or ''
        if mimetype.startswith('image/'):
            return 'image'
        if mimetype.startswith('video/'):
            return 'video'
        if mimetype.startswith('audio/'):
            return 'audio'
        return 'document'

    def _upload_whatsapp_media(self, attachment):
        """Sube un archivo al Graph API de Meta y devuelve el media id
        que luego se referencia en el mensaje saliente."""
        self.ensure_one()
        token, phone_number_id, api_version = self._get_meta_credentials()
        url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/media"
        mimetype = attachment.mimetype or mimetypes.guess_type(attachment.name or '')[0] \
            or 'application/octet-stream'
        files = {
            'file': (attachment.name, base64.b64decode(attachment.datas), mimetype),
        }
        response = self._meta_request(
            'POST', url, headers={"Authorization": f"Bearer {token}"},
            data={'messaging_product': 'whatsapp'}, files=files, timeout=60)
        response.raise_for_status()
        return response.json()['id']

    def action_send_message(self, body=False, attachments=None, reply_to_id=False):
        """Punto de entrada único usado por la interfaz de chat: envía
        texto y/o uno o varios archivos adjuntos (arrastrados o
        seleccionados) en la misma conversación.

        :param attachments: lista de dicts {name, mimetype, data(base64)}
        """
        self.ensure_one()
        self._check_can_send()
        if self.channel_type != 'whatsapp':
            raise UserError(_("Los adjuntos aún solo están implementados "
                               "para WhatsApp en este módulo base."))
        attachments = attachments or []
        if not attachments:
            if not body:
                raise UserError(_("Escribe un mensaje o adjunta un archivo."))
            return self.action_send_text(body, reply_to_id=reply_to_id)

        reply_to = self._get_reply_context(reply_to_id)
        token, phone_number_id, api_version = self._get_meta_credentials()
        url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"
        headers = {"Authorization": f"Bearer {token}"}
        messages = self.env['chatroom.message']

        for index, att_vals in enumerate(attachments):
            attachment = self.env['ir.attachment'].create({
                'name': att_vals.get('name') or 'archivo',
                'mimetype': att_vals.get('mimetype'),
                'datas': att_vals['data'],
            })
            media_type = self._meta_media_type(attachment.mimetype)
            caption = body if index == 0 else False
            # La cita solo tiene sentido en el primer adjunto del lote: cada
            # adjunto es un mensaje de WhatsApp aparte, y citar el mismo
            # mensaje varias veces seguidas no aporta nada.
            reply_here = reply_to if index == 0 else False

            message = self.env['chatroom.message'].create({
                'channel_id': self.id,
                'direction': 'outbound',
                'message_type': media_type,
                'body': caption,
                'state': 'sent',
                'date': fields.Datetime.now(),
                'attachment_ids': [(4, attachment.id)],
                'sender_user_id': self.env.user.id,
                'reply_to_id': reply_here.id if reply_here else False,
            })

            try:
                media_id = self._upload_whatsapp_media(attachment)
                media_payload = {'id': media_id}
                if caption and media_type in ('image', 'video', 'document'):
                    media_payload['caption'] = caption
                payload = {
                    "messaging_product": "whatsapp",
                    "to": self.external_id,
                    "type": media_type,
                    media_type: media_payload,
                }
                if reply_here:
                    payload["context"] = {"message_id": reply_here.wa_message_id}
                response = self._meta_request('POST', url, json=payload, headers=headers, timeout=60)
                response.raise_for_status()
                data = response.json()
                wa_message_id = data.get('messages', [{}])[0].get('id')
                message.write({'wa_message_id': wa_message_id})
            except (requests.RequestException, KeyError) as exc:
                _logger.error("Error enviando adjunto de WhatsApp: %s", exc)
                message.write({'state': 'failed'})
                messages |= message
                self._notify_thread_update()
                raise UserError(_("No se pudo enviar el archivo: %s") % exc)

            messages |= message

        self.write({
            'last_message_date': fields.Datetime.now(),
            'state': 'open',
        })
        self._notify_thread_update()
        return messages

    def action_send_reaction(self, message_id, emoji):
        """Reacciona con un emoji a un mensaje puntual (estilo WhatsApp: la
        reacción se pega al mensaje citado, no genera un mensaje nuevo en
        el hilo). Mandar emoji='' quita la reacción que había."""
        self.ensure_one()
        self._check_can_send()
        if self.channel_type != 'whatsapp':
            raise UserError(_("Las reacciones solo están implementadas "
                               "para WhatsApp en este módulo base."))
        target = self.env['chatroom.message'].browse(message_id)
        if not target.exists() or target.channel_id.id != self.id:
            raise UserError(_("No se puede reaccionar a ese mensaje."))
        if not target.wa_message_id:
            raise UserError(_(
                "No se puede reaccionar: este mensaje todavía no tiene un "
                "ID de WhatsApp confirmado (puede estar fallido o "
                "pendiente de enviarse)."))

        token, phone_number_id, api_version = self._get_meta_credentials()
        url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": self.external_id,
            "type": "reaction",
            "reaction": {"message_id": target.wa_message_id, "emoji": emoji or ""},
        }
        headers = {"Authorization": f"Bearer {token}"}
        try:
            response = self._meta_request('POST', url, json=payload, headers=headers, timeout=15)
            response.raise_for_status()
        except requests.RequestException as exc:
            _logger.error("Error enviando reacción de WhatsApp: %s", exc)
            raise UserError(_("No se pudo enviar la reacción: %s") % exc)

        target.write({'own_reaction': emoji or False})
        self._notify_thread_update()
        return True

    # ------------------------------------------------------------------
    # Reintentar un mensaje que falló (a mano, desde el chat, o solo
    # desde el cron de reintentos automáticos)
    # ------------------------------------------------------------------
    def action_retry_message(self, message_id):
        self.ensure_one()
        message = self.env['chatroom.message'].browse(message_id)
        if not message.exists() or message.channel_id.id != self.id \
                or message.direction != 'outbound':
            raise UserError(_("No se puede reintentar este mensaje."))
        if message.message_type in ('template', 'interactive'):
            raise UserError(_(
                "Las plantillas y los botones de respuesta rápida no se "
                "pueden reintentar automáticamente: mandalos de nuevo "
                "desde el composer."))
        if message.state != 'failed':
            return True

        self._check_can_send()
        message.retry_count += 1

        if self.channel_type != 'whatsapp':
            return self._retry_meta_page_text(message)

        token, phone_number_id, api_version = self._get_meta_credentials()
        url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"
        headers = {"Authorization": f"Bearer {token}"}

        try:
            if message.attachment_ids:
                attachment = message.attachment_ids[0]
                media_id = self._upload_whatsapp_media(attachment)
                media_payload = {'id': media_id}
                if message.body and message.message_type in ('image', 'video', 'document'):
                    media_payload['caption'] = message.body
                payload = {
                    "messaging_product": "whatsapp",
                    "to": self.external_id,
                    "type": message.message_type,
                    message.message_type: media_payload,
                }
            else:
                payload = {
                    "messaging_product": "whatsapp",
                    "to": self.external_id,
                    "type": "text",
                    "text": {"body": message.body},
                }
            response = self._meta_request('POST', url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            wa_message_id = data.get('messages', [{}])[0].get('id')
            message.write({'wa_message_id': wa_message_id, 'state': 'sent'})
        except (requests.RequestException, KeyError) as exc:
            _logger.error("Error reintentando el mensaje %s: %s", message.id, exc)
            message.write({'state': 'failed'})
            raise UserError(_("No se pudo reenviar el mensaje: %s") % exc)

        self.write({'last_message_date': fields.Datetime.now(), 'state': 'open'})
        self._notify_thread_update()
        return True

    def _retry_meta_page_text(self, message):
        """Reintento para Messenger/Instagram: hoy solo se reintenta
        texto (los adjuntos salientes por esos canales no están
        implementados, ver action_send_message)."""
        self.ensure_one()
        token, api_version = self._get_meta_page_credentials()
        url = f"https://graph.facebook.com/{api_version}/me/messages"
        payload = {
            "recipient": {"id": self.external_id},
            "message": {"text": message.body},
            "messaging_type": "RESPONSE",
        }
        headers = {"Authorization": f"Bearer {token}"}
        try:
            response = self._meta_request('POST', url, json=payload, headers=headers, timeout=15)
            response.raise_for_status()
            message.write({'wa_message_id': response.json().get('message_id'), 'state': 'sent'})
        except requests.RequestException as exc:
            message.write({'state': 'failed'})
            raise UserError(_("No se pudo reenviar el mensaje: %s") % exc)
        self.write({'last_message_date': fields.Datetime.now(), 'state': 'open'})
        self._notify_thread_update()
        return True

    @api.model
    def _cron_retry_failed_messages(self):
        """Reintenta solo, en segundo plano, mensajes fallidos recientes
        (menos de 1 hora, hasta 3 veces): un corte de red pasajero no
        debería obligar al agente a darse cuenta y reintentar a mano."""
        cutoff = fields.Datetime.subtract(fields.Datetime.now(), hours=1)
        failed = self.env['chatroom.message'].search([
            ('direction', '=', 'outbound'),
            ('state', '=', 'failed'),
            ('message_type', 'not in', ('template', 'interactive')),
            ('retry_count', '<', 3),
            ('date', '>=', cutoff),
        ], limit=50)
        for message in failed:
            try:
                message.channel_id.action_retry_message(message.id)
            except UserError as exc:
                _logger.info(
                    "Reintento automático omitido para el mensaje %s: %s", message.id, exc)

    # ------------------------------------------------------------------
    # Mensajes programados: se guardan aparte (chatroom.scheduled.message)
    # y un cron los va enviando; no son chatroom.message hasta que salen
    # de verdad, para no mostrar en el hilo algo que todavía no se mandó.
    # ------------------------------------------------------------------
    def action_schedule_message(self, body, scheduled_date):
        self.ensure_one()
        if not (body or '').strip():
            raise UserError(_("Escribe un mensaje para programar."))
        if not scheduled_date or fields.Datetime.to_datetime(scheduled_date) <= fields.Datetime.now():
            raise UserError(_("La fecha programada tiene que ser en el futuro."))
        record = self.env['chatroom.scheduled.message'].create({
            'channel_id': self.id,
            'body': body,
            'scheduled_date': scheduled_date,
        })
        return record.id

    def get_scheduled_messages(self):
        self.ensure_one()
        records = self.env['chatroom.scheduled.message'].search(
            [('channel_id', '=', self.id), ('state', '=', 'pending')], order='scheduled_date asc')
        return [{
            'id': r.id,
            'body': r.body,
            'scheduled_date': r.scheduled_date,
        } for r in records]

    def action_cancel_scheduled_message(self, scheduled_id):
        self.ensure_one()
        record = self.env['chatroom.scheduled.message'].browse(scheduled_id)
        if record.exists() and record.channel_id.id == self.id:
            record.action_cancel()
        return True

    def action_send_template(self, template_name, language_code, variables=None):
        """Envía una plantilla aprobada por Meta (HSM). Es la única forma
        de iniciar/retomar conversación fuera de la ventana de 24h."""
        self.ensure_one()
        self._check_can_send()
        if self.channel_type != 'whatsapp':
            raise UserError(_("El envío directo aún solo está implementado "
                               "para WhatsApp en este módulo base."))
        token, phone_number_id, api_version = self._get_meta_credentials()
        url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"
        components = []
        if variables:
            components.append({
                "type": "body",
                "parameters": [{"type": "text", "text": value} for value in variables],
            })
        payload = {
            "messaging_product": "whatsapp",
            "to": self.external_id,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
                "components": components,
            },
        }
        headers = {"Authorization": f"Bearer {token}"}

        message = self.env['chatroom.message'].create({
            'channel_id': self.id,
            'direction': 'outbound',
            'message_type': 'template',
            'body': _("[Plantilla: %s]") % template_name,
            'state': 'sent',
            'date': fields.Datetime.now(),
            'sender_user_id': self.env.user.id,
        })
        try:
            response = self._meta_request('POST', url, json=payload, headers=headers, timeout=15)
            response.raise_for_status()
            wa_message_id = response.json().get('messages', [{}])[0].get('id')
            message.write({'wa_message_id': wa_message_id})
        except requests.RequestException as exc:
            _logger.error("Error enviando plantilla de WhatsApp: %s", exc)
            message.write({'state': 'failed'})
            raise UserError(_("No se pudo enviar la plantilla: %s") % exc)

        self.write({'last_message_date': fields.Datetime.now(), 'state': 'open'})
        self._notify_thread_update()
        return message

    def action_send_interactive_buttons(self, body, buttons):
        """Envía un mensaje con hasta 3 botones de respuesta rápida
        (WhatsApp Interactive Messages). La respuesta del cliente llega
        por el webhook como un mensaje 'interactive' normal."""
        self.ensure_one()
        self._check_can_send()
        if self.channel_type != 'whatsapp':
            raise UserError(_("El envío directo aún solo está implementado "
                               "para WhatsApp en este módulo base."))
        buttons = [b.strip() for b in (buttons or []) if b and b.strip()][:3]
        if not buttons:
            raise UserError(_("Agrega al menos un botón."))

        token, phone_number_id, api_version = self._get_meta_credentials()
        url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": self.external_id,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body or _("Elige una opción:")},
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": f"btn_{index}", "title": label[:20]}}
                        for index, label in enumerate(buttons)
                    ],
                },
            },
        }
        headers = {"Authorization": f"Bearer {token}"}

        message = self.env['chatroom.message'].create({
            'channel_id': self.id,
            'direction': 'outbound',
            'message_type': 'interactive',
            'body': "\n".join([body] + [f"[{label}]" for label in buttons]) if body
                    else "\n".join(f"[{label}]" for label in buttons),
            'state': 'sent',
            'date': fields.Datetime.now(),
            'sender_user_id': self.env.user.id,
        })
        try:
            response = self._meta_request('POST', url, json=payload, headers=headers, timeout=15)
            response.raise_for_status()
            wa_message_id = response.json().get('messages', [{}])[0].get('id')
            message.write({'wa_message_id': wa_message_id})
        except requests.RequestException as exc:
            _logger.error("Error enviando botones de WhatsApp: %s", exc)
            message.write({'state': 'failed'})
            raise UserError(_("No se pudo enviar el mensaje: %s") % exc)

        self.write({'last_message_date': fields.Datetime.now(), 'state': 'open'})
        self._notify_thread_update()
        return message

    def _send_interactive_list(self, body, button_label, rows, message_type_body):
        """Base común para mensajes interactivos tipo 'lista' (hasta 10
        filas, a diferencia de los botones que solo permiten 3): la
        encuesta de satisfacción y el catálogo de productos la reusan."""
        self.ensure_one()
        self._check_can_send()
        if self.channel_type != 'whatsapp':
            raise UserError(_("El envío directo aún solo está implementado "
                               "para WhatsApp en este módulo base."))
        token, phone_number_id, api_version = self._get_meta_credentials()
        url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": self.external_id,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": body},
                "action": {
                    "button": button_label[:20],
                    "sections": [{"rows": rows}],
                },
            },
        }
        headers = {"Authorization": f"Bearer {token}"}

        message = self.env['chatroom.message'].create({
            'channel_id': self.id,
            'direction': 'outbound',
            'message_type': 'interactive',
            'body': message_type_body,
            'state': 'sent',
            'date': fields.Datetime.now(),
            'sender_user_id': self.env.user.id,
        })
        try:
            response = self._meta_request('POST', url, json=payload, headers=headers, timeout=15)
            response.raise_for_status()
            wa_message_id = response.json().get('messages', [{}])[0].get('id')
            message.write({'wa_message_id': wa_message_id})
        except requests.RequestException as exc:
            _logger.error("Error enviando mensaje de lista de WhatsApp: %s", exc)
            message.write({'state': 'failed'})
            raise UserError(_("No se pudo enviar el mensaje: %s") % exc)

        self.write({'last_message_date': fields.Datetime.now(), 'state': 'open'})
        self._notify_thread_update()
        return message

    def action_send_csat_survey(self):
        """Manda la encuesta de satisfacción (1 a 5) como mensaje de lista
        interactiva. Se llama sola al cerrar la conversación, pero también
        se puede volver a mandar a mano desde el botón del formulario."""
        self.ensure_one()
        rows = [
            {"id": f"csat_{score}", "title": "⭐" * score, "description": label}
            for score, label in (
                (1, _("Muy mala")), (2, _("Mala")), (3, _("Regular")),
                (4, _("Buena")), (5, _("Excelente")))
        ]
        message = self._send_interactive_list(
            _("¿Cómo calificarías la atención que recibiste? (1 a 5 estrellas)"),
            _("Calificar"), rows, _("[Encuesta de satisfacción]"))
        self.csat_requested = True
        return message

    def action_send_product_catalog(self, product_ids):
        """Manda hasta 10 productos como lista interactiva para que el
        cliente elija con un toque. No requiere tener armado un Catálogo
        de Meta Commerce Manager (API y sincronización de feed aparte,
        que la mayoría de las pymes no tiene configurado): alcanza con
        productos de Odoo. Al tocar uno, el webhook lo agrega directo al
        carrito de esta conversación (ver _handle_interactive_reply)."""
        self.ensure_one()
        if 'product.product' not in self.env:
            raise UserError(_("El módulo de Ventas no está instalado."))
        products = self.env['product.product'].browse(product_ids)[:10]
        if not products:
            raise UserError(_("Elegí al menos un producto."))
        currency = self.env.company.currency_id
        rows = [
            {"id": f"prod_{product.id}",
             "title": product.display_name[:24],
             "description": f"{product.list_price:.2f} {currency.symbol}"}
            for product in products
        ]
        return self._send_interactive_list(
            _("Estos son nuestros productos, tocá el que te interese:"),
            _("Ver productos"), rows, _("[Catálogo de productos]"))

    def _maybe_send_csat_survey(self):
        """Dispara la encuesta de satisfacción al cerrar, sin romper el
        cierre si falla el envío (sin credenciales, cliente dado de baja,
        etc.) ni volver a preguntar si ya se preguntó o ya contestó."""
        self.ensure_one()
        if (self.channel_type != 'whatsapp' or self.csat_requested
                or self.csat_score or not self.message_ids):
            return
        try:
            self.action_send_csat_survey()
        except UserError:
            _logger.info(
                "No se pudo enviar la encuesta de satisfacción en el canal %s", self.id)

    def _record_csat_response(self, score):
        """Guarda la calificación que contestó el cliente. Si llega un
        valor fuera de 1-5 (id manipulado o mensaje inesperado) se
        ignora en vez de guardar basura."""
        self.ensure_one()
        if not self.csat_requested or score not in range(1, 6):
            return
        self.write({
            'csat_score': score,
            'csat_requested': False,
            'csat_answered_at': fields.Datetime.now(),
        })
        self.message_post(
            body=_("El cliente calificó la atención con %s/5.") % score,
            subtype_xmlid='mail.mt_note',
        )

    def _handle_interactive_reply(self, msg_type, msg):
        """Interpreta la respuesta a un mensaje interactivo propio
        (encuesta de satisfacción, catálogo de productos) a partir del
        'id' de la fila/botón elegido -viene en el payload crudo del
        webhook, no en el mensaje ya guardado, porque el texto visible
        (el título) no alcanza para distinguir de forma confiable qué
        opción tocó el cliente."""
        self.ensure_one()
        if msg_type != 'interactive':
            return
        interactive = msg.get('interactive') or {}
        reply = interactive.get('list_reply') or interactive.get('button_reply') or {}
        reply_id = reply.get('id') or ''
        if reply_id.startswith('csat_'):
            try:
                self._record_csat_response(int(reply_id.split('_', 1)[1]))
            except (ValueError, IndexError):
                pass
        elif reply_id.startswith('prod_'):
            try:
                product = self.env['product.product'].browse(int(reply_id.split('_', 1)[1]))
            except (ValueError, IndexError):
                return
            if product.exists():
                self._add_to_cart(product, 1)
                self.message_post(
                    body=_("Se agregó \"%s\" al carrito desde el catálogo de WhatsApp.")
                    % product.display_name,
                    subtype_xmlid='mail.mt_note',
                )
                self._notify_thread_update()

    def _notify_thread_update(self):
        """Notifica por el bus a quien tenga abierta la conversación (y al
        ícono de la barra superior) para refrescar en tiempo real, sin
        recargar la página."""
        for rec in self:
            self.env['bus.bus']._sendone(
                f'chatroom_channel_{rec.id}', 'chatroom.message/new',
                {'channel_id': rec.id})
            self.env['bus.bus']._sendone(
                'chatroom_whatsapp_global', 'chatroom.message/new',
                {'channel_id': rec.id})

    def _notify_new_inbound_message(self, message):
        """Evento aparte (más liviano de escuchar) para la notificación de
        escritorio/sonido del ícono de la barra superior: solo se manda
        cuando llega un mensaje nuevo del cliente, no en cada refresco
        general (enviar, marcar leído, etc.)."""
        self.ensure_one()
        self.env['bus.bus']._sendone(
            'chatroom_whatsapp_global', 'chatroom.message/inbound', {
                'channel_id': self.id,
                'assigned_user_id': self.assigned_user_id.id or False,
                'partner_name': self.partner_id.name or self.external_id,
                'preview': (message.body or '')[:120],
            })

    def action_mark_read(self):
        """Marca como leídos los mensajes entrantes pendientes y le avisa
        a Meta (check azul del lado del cliente). Se llama al abrir la
        conversación; nunca debe romper la UI si falla el acuse remoto."""
        self.ensure_one()
        unread = self.message_ids.filtered(
            lambda m: m.direction == 'inbound' and m.state != 'read')
        if not unread:
            return False

        last = unread.sorted('date', reverse=True)[:1]
        if self.channel_type == 'whatsapp' and last.wa_message_id:
            try:
                token, phone_number_id, api_version = self._get_meta_credentials()
                url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"
                self._meta_request(
                    'POST', url,
                    json={
                        "messaging_product": "whatsapp",
                        "status": "read",
                        "message_id": last.wa_message_id,
                    },
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=10, max_retries=1,
                )
            except (UserError, requests.RequestException) as exc:
                _logger.warning("No se pudo enviar el acuse de lectura (canal %s): %s", self.id, exc)

        unread.write({'state': 'read'})
        return True

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------
    @api.model
    def get_dashboard_data(self, agent_limit=8):
        """Datos agregados para el dashboard de Chatroom: se calculan acá
        (con read_group, no trayendo registros al cliente) para que la
        pantalla cargue con pocas consultas livianas."""
        today_start = fields.Datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        month_ago = fields.Datetime.subtract(fields.Datetime.now(), days=30)

        pending_count = self.search_count([('state', '=', 'pending')])
        today_count = self.search_count([('last_message_date', '>=', today_start)])
        messages_today = self.env['chatroom.message'].search_count(
            [('date', '>=', today_start)])

        [(unread_total,)] = self._read_group(
            [('state', '!=', 'closed')], [], ['unread_count:sum']) or [(0,)]

        responded = self._read_group(
            [('create_date', '>=', month_ago), ('first_response_minutes', '>', 0)],
            [], ['first_response_minutes:avg'])
        avg_first_response = responded[0][0] if responded else 0.0

        by_agent = self._read_group(
            [('state', 'in', ('open', 'pending')), ('assigned_user_id', '!=', False)],
            ['assigned_user_id'], ['__count'],
            order='__count desc', limit=agent_limit)

        response_by_agent = self._read_group(
            [('create_date', '>=', month_ago), ('first_response_minutes', '>', 0),
             ('assigned_user_id', '!=', False)],
            ['assigned_user_id'], ['first_response_minutes:avg'],
            order='first_response_minutes:avg asc', limit=agent_limit)

        # SLA: sobre las conversaciones que ya tuvieron primera respuesta
        # en los últimos 30 días, qué porcentaje la tuvo antes del umbral
        # de "vencido" (mismo umbral que pinta el semáforo en vivo).
        sla_answered_count = self.search_count(
            [('create_date', '>=', month_ago), ('first_response_minutes', '>', 0)])
        sla_compliant_count = self.search_count([
            ('create_date', '>=', month_ago), ('first_response_minutes', '>', 0),
            ('first_response_minutes', '<', SLA_FIRST_RESPONSE_RED_MINUTES),
        ])
        sla_compliance_rate = (
            round(sla_compliant_count / sla_answered_count * 100, 1)
            if sla_answered_count else None)

        # CSAT: promedio de las encuestas contestadas en los últimos 30
        # días (csat_score solo tiene un valor real una vez que el
        # cliente respondió; ver _record_csat_response).
        csat_answered_count = self.search_count(
            [('csat_answered_at', '>=', month_ago), ('csat_score', '>', 0)])
        csat_avg_group = self._read_group(
            [('csat_answered_at', '>=', month_ago), ('csat_score', '>', 0)],
            [], ['csat_score:avg'])
        avg_csat_score = csat_avg_group[0][0] if csat_avg_group else 0.0

        raw_last_webhook = self.env['ir.config_parameter'].sudo().get_param(
            'chatroom_whatsapp.last_webhook_at')
        last_webhook = fields.Datetime.to_datetime(raw_last_webhook) if raw_last_webhook else False

        return {
            'last_webhook_display': self._format_relative_time(last_webhook),
            'last_webhook_ok': bool(
                last_webhook and fields.Datetime.now() - last_webhook < timedelta(hours=24)),
            'pending_count': pending_count,
            'today_count': today_count,
            'messages_today': messages_today,
            'unread_total': unread_total or 0,
            'avg_first_response_minutes': round(avg_first_response or 0.0, 1),
            'by_agent': [
                {'name': user.name, 'count': count}
                for user, count in by_agent
            ],
            'response_by_agent': [
                {'name': user.name, 'minutes': round(minutes, 1)}
                for user, minutes in response_by_agent
            ],
            'sla_compliance_rate': sla_compliance_rate,
            'sla_answered_count': sla_answered_count,
            'avg_csat_score': round(avg_csat_score or 0.0, 2),
            'csat_answered_count': csat_answered_count,
        }

    # ------------------------------------------------------------------
    # Inteligencia Artificial: sugerencia, clasificación y automatización
    # ------------------------------------------------------------------
    def _ai_get_credentials(self):
        icp = self.env['ir.config_parameter'].sudo()
        if not icp.get_param('chatroom_whatsapp.ai_enabled'):
            return None
        api_url = icp.get_param('chatroom_whatsapp.ai_provider_url')
        api_key = icp.get_param('chatroom_whatsapp.ai_api_key')
        model = icp.get_param('chatroom_whatsapp.ai_model', 'gpt-4o-mini')
        if not api_url or not api_key:
            return None
        return api_url, api_key, model

    def _ai_chat_completion(self, messages):
        """Llama al endpoint 'chat completions' configurado (cualquier
        proveedor LLM compatible: OpenAI, Anthropic vía proxy, Azure, un
        modelo propio, etc.) y devuelve el texto de la respuesta."""
        creds = self._ai_get_credentials()
        if not creds:
            raise UserError(_(
                "Activa y configura la IA en Ajustes > Chatroom WhatsApp."))
        api_url, api_key, model = creds
        response = self._meta_request(
            'POST', api_url,
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model, "messages": messages},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    def _ai_build_conversation(self, extra_system=None):
        self.ensure_one()
        history = self.message_ids.sorted('date')[-10:]
        conversation = [
            {"role": "user" if m.direction == 'inbound' else "assistant",
             "content": m.body or ''}
            for m in history if m.body
        ]
        system_prompt = extra_system or _(
            "Eres un asistente de atención al cliente por WhatsApp. "
            "Responde en español, de forma breve, cordial y orientada a "
            "avanzar la venta o resolver la consulta del cliente.")
        return [{"role": "system", "content": system_prompt}] + conversation

    def action_ai_suggest_reply(self):
        self.ensure_one()
        try:
            self.ai_suggested_reply = self._ai_chat_completion(self._ai_build_conversation())
        except (requests.RequestException, KeyError, IndexError) as exc:
            _logger.error("Error consultando IA: %s", exc)
            raise UserError(_("No se pudo obtener una sugerencia de IA: %s") % exc)
        return True

    def action_send_ai_suggestion(self):
        self.ensure_one()
        if not self.ai_suggested_reply:
            raise UserError(_("No hay ninguna sugerencia de IA generada."))
        self.action_send_text(self.ai_suggested_reply)
        self.ai_suggested_reply = False
        return True

    def action_ai_summarize(self):
        self.ensure_one()
        system_prompt = _(
            "Resume esta conversación de WhatsApp para un agente humano "
            "que se está poniendo al día. Responde en español, en un "
            "párrafo corto (máximo 5 líneas), mencionando qué quiere el "
            "cliente y en qué quedó la conversación hasta ahora.")
        try:
            self.ai_summary = self._ai_chat_completion(
                self._ai_build_conversation(extra_system=system_prompt))
        except (requests.RequestException, KeyError, IndexError) as exc:
            _logger.error("Error consultando IA: %s", exc)
            raise UserError(_("No se pudo generar el resumen con IA: %s") % exc)
        return True

    def _ai_classify_intent(self):
        self.ensure_one()
        system_prompt = _(
            "Clasifica la intención del cliente en esta conversación de "
            "WhatsApp. Responde ÚNICAMENTE con un JSON de la forma "
            '{"intent": "consulta|venta|soporte|queja"}, sin texto '
            "adicional ni explicaciones.")
        raw = self._ai_chat_completion(self._ai_build_conversation(extra_system=system_prompt))
        try:
            intent = json.loads(raw).get('intent')
        except (ValueError, AttributeError):
            intent = None
        valid_intents = dict(self._fields['ai_intent'].selection)
        return intent if intent in valid_intents else 'otro'

    def _ai_search_products_mentioned(self, text, limit=5):
        """Busca productos vendibles cuyo nombre el cliente mencionó en su
        mensaje, para poder responder consultas de precio (y armar el
        carrito) con datos reales en vez de dejar que el modelo los
        invente.

        Búsqueda simple y a propósito literal (palabras de 4+ letras del
        mensaje, comparadas contra el nombre del producto): nada de
        embeddings ni fuzzy match, para que sea 100% predecible qué datos
        se le terminan pasando a la IA como "verdad". Busca sobre
        product.product (variantes), no product.template, porque es lo
        mismo que espera sale.order.line y lo que ya usan
        search_products/action_send_product.
        """
        self.ensure_one()
        if 'product.product' not in self.env:
            return self.env['product.product']
        words = {w.lower() for w in re.findall(r'\w{4,}', text or '', re.UNICODE)}
        if not words:
            return self.env['product.product']
        name_domain = [('name', 'ilike', w) for w in words]
        if len(name_domain) > 1:
            name_domain = ['|'] * (len(name_domain) - 1) + name_domain
        domain = [('sale_ok', '=', True), ('active', '=', True)] + name_domain
        return self.env['product.product'].search(domain, limit=limit)

    def _ai_price_context_system_message(self, products):
        currency = self.env.company.currency_id
        lines = [
            f"- {product.name}: {product.list_price:.2f} {currency.symbol}"
            for product in products
        ]
        return _(
            "Estos son los ÚNICOS precios reales disponibles ahora mismo "
            "para productos que el cliente mencionó. Si respondés sobre "
            "precios, usá EXCLUSIVAMENTE estos datos; si el cliente "
            "pregunta por algo que no está en esta lista, decile que no "
            "tenés esa información a mano y que un agente lo va a "
            "confirmar. Nunca inventes un precio que no esté acá:\n%s"
        ) % "\n".join(lines)

    def _ai_reply_with_product_prices(self, products):
        self.ensure_one()
        system_prompt = self._ai_price_context_system_message(products) + "\n\n" + _(
            "Sos un asistente de ventas por WhatsApp. Con los datos de "
            "arriba, respondé en español, breve y cordial, la consulta "
            "de precio del cliente.")
        reply = self._ai_chat_completion(self._ai_build_conversation(extra_system=system_prompt))
        self.action_send_text(reply)

    # ------------------------------------------------------------------
    # Vendedor automático: la IA arma un carrito charlando con el cliente
    # y arma una Cotización real cuando confirma, pero SIEMPRE queda en
    # borrador para que un agente humano la revise antes de confirmarla
    # -la IA nunca la confirma sola, no toca stock ni factura nada.
    # ------------------------------------------------------------------
    def _add_to_cart(self, product, qty):
        self.ensure_one()
        existing = self.cart_line_ids.filtered(lambda line: line.product_id == product.id)
        if existing:
            existing.quantity += qty
        else:
            self.env['chatroom.cart.line'].create({
                'channel_id': self.id,
                'product_id': product.id,
                'product_name': product.display_name,
                'quantity': qty,
                'price_unit': product.list_price,
            })

    def action_remove_cart_line(self, line_id):
        self.ensure_one()
        line = self.env['chatroom.cart.line'].browse(line_id)
        if line.exists() and line.channel_id.id == self.id:
            line.unlink()
        return True

    def action_checkout_cart(self):
        """Convierte el carrito en una Cotización real de Ventas
        (sale.order en borrador). No la confirma: queda para que un
        agente la revise, ajuste precios/descuentos si hace falta y
        recién ahí la confirme desde el formulario normal de Odoo."""
        self.ensure_one()
        if not self.sale_installed:
            raise UserError(_("El módulo de Ventas no está instalado."))
        if not self.cart_line_ids:
            raise UserError(_("El carrito está vacío."))
        if not self.partner_id:
            raise UserError(_(
                "Esta conversación no tiene un contacto vinculado; no se "
                "puede armar una cotización."))
        order_lines = []
        for line in self.cart_line_ids:
            product = self.env['product.product'].browse(line.product_id)
            if product.exists():
                order_lines.append((0, 0, {
                    'product_id': product.id,
                    'product_uom_qty': line.quantity,
                }))
        if not order_lines:
            raise UserError(_(
                "Ninguno de los productos del carrito existe todavía; no "
                "se pudo armar la cotización."))
        order = self.env['sale.order'].create({
            'partner_id': self.partner_id.id,
            'order_line': order_lines,
        })
        self.cart_line_ids.unlink()
        self.message_post(
            body=_(
                "Se armó la cotización %s a partir del carrito de esta "
                "conversación. Queda pendiente de revisión antes de "
                "confirmarla."
            ) % order.name,
            subtype_xmlid='mail.mt_note',
        )
        if self.assigned_user_id and self.assigned_user_id.partner_id:
            self.message_post(
                body=_("La IA armó una cotización nueva (%s) para que la "
                       "revises antes de confirmarla.") % order.name,
                partner_ids=[self.assigned_user_id.partner_id.id],
                subtype_xmlid='mail.mt_comment',
            )
        return order.id

    def _ai_run_order_assistant(self, matched_products):
        """Vendedor automático: le pide a la IA que decida, en JSON
        estricto (compatible con cualquier proveedor, sin depender de
        'function calling' propietario de un proveedor en particular),
        si hay que agregar algo al carrito, cerrar el pedido, o solo
        contestar. Python ejecuta esa decisión de forma determinística
        -la IA nunca toca la base de datos directamente, solo elige
        entre 3 acciones fijas."""
        self.ensure_one()
        currency = self.env.company.currency_id
        catalog_lines = "\n".join(
            f"- id {p.id}: {p.display_name} - {p.list_price:.2f} {currency.symbol}"
            for p in matched_products
        ) or "(el cliente no mencionó ahora ningún producto que exista)"
        cart_lines = "\n".join(
            f"- {line.product_name} x{line.quantity:g}" for line in self.cart_line_ids
        ) or "(vacío)"
        system_prompt = _(
            "Sos un vendedor automático por WhatsApp. Respondé "
            "ÚNICAMENTE con un JSON, sin texto extra ni markdown, de una "
            "de estas 3 formas exactas:\n"
            '{"action": "add_items", "items": [{"product_id": <id>, '
            '"qty": <numero>}], "reply": "<texto>"}\n'
            '{"action": "checkout", "reply": "<texto>"}\n'
            '{"action": "reply", "reply": "<texto>"}\n\n'
            "Usá 'add_items' SOLO con ids de la lista de productos de "
            "abajo (nunca inventes un id ni un precio nuevo). Usá "
            "'checkout' solo cuando el cliente confirme que quiere "
            "cerrar el pedido Y el carrito no esté vacío. Usá 'reply' "
            "para saludos, preguntas, o productos que no están en la "
            "lista (avisale que no lo tenés a mano y que un agente lo va "
            "a confirmar). 'reply' siempre lleva el mensaje en español "
            "que se le manda al cliente por WhatsApp, breve y cordial; "
            "si de verdad no hace falta contestar nada dejalo vacío.\n\n"
            "Carrito actual del cliente:\n%(cart)s\n\n"
            "Productos reales que mencionó recién (únicos válidos para "
            "add_items):\n%(catalog)s"
        ) % {'cart': cart_lines, 'catalog': catalog_lines}

        raw = self._ai_chat_completion(self._ai_build_conversation(extra_system=system_prompt))
        try:
            data = json.loads(raw)
        except ValueError:
            _logger.warning(
                "Respuesta de IA no es JSON válido en canal %s: %r", self.id, raw)
            return
        action = data.get('action')
        reply = (data.get('reply') or '').strip()

        if action == 'add_items':
            matched_by_id = {p.id: p for p in matched_products}
            for item in (data.get('items') or []):
                product = matched_by_id.get(item.get('product_id'))
                qty = item.get('qty')
                if not product or not isinstance(qty, (int, float)) or qty <= 0:
                    continue
                self._add_to_cart(product, qty)
        elif action == 'checkout':
            if self.cart_line_ids:
                self.action_checkout_cart()
            elif not reply:
                reply = _("Todavía no agregaste nada al carrito.")

        if reply:
            self.action_send_text(reply)

    def _ai_process_inbound_message(self, message):
        """Automatizaciones opcionales al recibir un mensaje: clasificar
        la intención, crear una oportunidad automáticamente si aplica y/o
        responder de forma autónoma. Se activan por separado en Ajustes;
        cualquier fallo se registra en el log sin interrumpir el webhook.
        No hace nada si un agente humano ya tomó la conversación
        (`ai_paused`)."""
        self.ensure_one()
        if self.ai_paused:
            return
        icp = self.env['ir.config_parameter'].sudo()
        if not icp.get_param('chatroom_whatsapp.ai_enabled'):
            return
        try:
            if icp.get_param('chatroom_whatsapp.ai_auto_classify'):
                self.ai_intent = self._ai_classify_intent()

            if (icp.get_param('chatroom_whatsapp.ai_auto_lead')
                    and self.ai_intent == 'venta' and not self.pinned_lead_id
                    and self.crm_installed and self.partner_id):
                self.action_create_lead()

            if icp.get_param('chatroom_whatsapp.ai_auto_order_reply') and message.body:
                matched_products = self._ai_search_products_mentioned(message.body)
                self._ai_run_order_assistant(matched_products)
                return

            if icp.get_param('chatroom_whatsapp.ai_auto_price_reply') and message.body:
                matched_products = self._ai_search_products_mentioned(message.body)
                if matched_products:
                    self._ai_reply_with_product_prices(matched_products)
                    return

            if icp.get_param('chatroom_whatsapp.ai_auto_reply'):
                self.action_ai_suggest_reply()
                self.action_send_ai_suggestion()
        except UserError as exc:
            _logger.warning("Automatización de IA omitida en canal %s: %s", self.id, exc)
        except Exception:  # noqa: BLE001 - no debe romper la ingesta del webhook
            _logger.exception("Error inesperado en automatización de IA (canal %s)", self.id)

    # ------------------------------------------------------------------
    # Flujo comercial: crear oportunidad / presupuesto desde la conversación
    # ------------------------------------------------------------------
    @staticmethod
    def _window_action(view_mode='list,form', **vals):
        """Arma una acción ir.actions.act_window ya lista para
        this.action.doAction() en JS.

        Un <button type="object"> de una vista clásica pasa por el
        endpoint call_button, que llama a clean_action() en el servidor
        y ahí se rellena 'views' a partir de 'view_mode' solo. Pero un
        orm.call() común (como usa el panel de contacto de la app) NO
        pasa por ahí: si el dict no trae 'views' ya armado, el webclient
        revienta con "Cannot read properties of undefined (reading
        'map')" al hacer action.views.map(...). Con este helper, estas
        acciones funcionan llamadas desde cualquiera de los dos lados.
        """
        vals.setdefault('views', [(False, mode) for mode in view_mode.split(',')])
        # Las acciones que salen del chat deben conservar el contexto de la
        # conversación. Se renderizan en un diálogo nativo de Odoo, no en
        # otra pestaña ni reemplazando la aplicación de chat.
        vals.setdefault('target', 'new')
        return {'type': 'ir.actions.act_window', 'view_mode': view_mode, **vals}

    @api.model
    def action_get_embedded_menu_action(self, xmlid):
        """Devuelve una acción de menú preparada para abrirse sobre el chat.

        El cliente no debe resolver XML IDs de forma arbitraria. Esta lista
        blanca mantiene el acceso limitado a las herramientas que el propio
        Chatroom muestra en su barra.
        """
        allowed = {
            'chatroom_whatsapp.action_chatroom_template',
            'chatroom_whatsapp.action_chatroom_whatsapp_number',
            'chatroom_whatsapp.action_chatroom_canned_response',
            'chatroom_whatsapp.action_chatroom_dashboard',
        }
        if xmlid not in allowed:
            raise UserError(_("Acción no disponible desde Chatroom."))
        action = self.env['ir.actions.actions']._for_xml_id(xmlid)
        action['target'] = 'new'
        return action

    def action_create_lead(self):
        self.ensure_one()
        if not self.crm_installed:
            raise UserError(_("El módulo CRM no está instalado."))
        lead = self.env['crm.lead'].create({
            'name': _("Oportunidad WhatsApp - %s") % (self.partner_id.name or self.external_id),
            'partner_id': self.partner_id.id,
            'phone': self.partner_id.phone,
            'description': self.ai_summary or "\n".join(
                f"[{m.direction}] {m.body}" for m in self.message_ids.sorted('date') if m.body),
        })
        self.pinned_lead_id = lead.id
        return self._window_action(
            res_model='crm.lead', res_id=lead.id, view_mode='form')

    def action_open_pinned_lead(self):
        self.ensure_one()
        if not self.crm_installed or not self.pinned_lead_id:
            return False
        return self._window_action(
            res_model='crm.lead', res_id=self.pinned_lead_id, view_mode='form')

    def action_create_quotation(self):
        self.ensure_one()
        if not self.sale_installed:
            raise UserError(_("El módulo Ventas no está instalado."))
        if not self.partner_id:
            raise UserError(_("La conversación no tiene un contacto asociado."))
        order = self.env['sale.order'].create({
            'partner_id': self.partner_id.id,
            'origin': self.display_name,
        })
        return self._window_action(
            res_model='sale.order', res_id=order.id, view_mode='form')

    def action_create_invoice(self):
        """Factura directa, sin pasar por un presupuesto antes — para
        ventas rápidas de contado que se cierran por WhatsApp."""
        self.ensure_one()
        if not self.account_installed:
            raise UserError(_("El módulo de Facturación no está instalado."))
        if not self.partner_id:
            raise UserError(_("La conversación no tiene un contacto asociado."))
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_id.id,
            'invoice_origin': self.display_name,
        })
        return self._window_action(
            res_model='account.move', res_id=invoice.id, view_mode='form')

    def action_create_purchase_order(self):
        """Para cuando el contacto de WhatsApp es un proveedor, no un
        cliente (ej. una línea de Compras que también atiende pedidos
        por WhatsApp)."""
        self.ensure_one()
        if not self.purchase_installed:
            raise UserError(_("El módulo de Compras no está instalado."))
        if not self.partner_id:
            raise UserError(_("La conversación no tiene un contacto asociado."))
        order = self.env['purchase.order'].create({
            'partner_id': self.partner_id.id,
            'origin': self.display_name,
        })
        return self._window_action(
            res_model='purchase.order', res_id=order.id, view_mode='form')

    def action_create_task(self):
        self.ensure_one()
        if not self.project_installed:
            raise UserError(_("El módulo Proyectos no está instalado."))
        if not self.partner_id:
            raise UserError(_("La conversación no tiene un contacto asociado."))
        task = self.env['project.task'].create({
            'name': _("WhatsApp - %s") % (self.partner_id.name or self.external_id),
            'partner_id': self.partner_id.id,
            'description': self.ai_summary or "\n".join(
                f"[{m.direction}] {m.body}" for m in self.message_ids.sorted('date') if m.body),
        })
        return self._window_action(
            res_model='project.task', res_id=task.id, view_mode='form')

    def action_view_tasks(self):
        self.ensure_one()
        return self._window_action(
            name=_("Tareas"), res_model='project.task', view_mode='list,kanban,form',
            domain=[('partner_id', '=', self.partner_id.id)],
            context={'default_partner_id': self.partner_id.id})

    def action_view_leads(self):
        self.ensure_one()
        return self._window_action(
            name=_("Oportunidades"), res_model='crm.lead', view_mode='list,kanban,form',
            domain=[('partner_id', '=', self.partner_id.id)],
            context={'default_partner_id': self.partner_id.id})

    def action_view_sale_orders(self):
        self.ensure_one()
        return self._window_action(
            name=_("Presupuestos y Pedidos"), res_model='sale.order', view_mode='list,form',
            domain=[('partner_id', '=', self.partner_id.id)],
            context={'default_partner_id': self.partner_id.id})

    def action_view_invoices(self):
        self.ensure_one()
        return self._window_action(
            name=_("Facturas"), res_model='account.move', view_mode='list,form',
            domain=[
                ('partner_id', '=', self.partner_id.id),
                ('move_type', 'in', ('out_invoice', 'out_refund')),
            ],
            context={'default_partner_id': self.partner_id.id, 'default_move_type': 'out_invoice'})

    def action_view_purchases(self):
        self.ensure_one()
        return self._window_action(
            name=_("Compras"), res_model='purchase.order', view_mode='list,form',
            domain=[('partner_id', '=', self.partner_id.id)],
            context={'default_partner_id': self.partner_id.id})

    # ------------------------------------------------------------------
    # Panel de contacto: datos + accesos rápidos a CRM/Ventas/Compras/
    # Facturas/Tareas + enviar un presupuesto o factura por WhatsApp.
    # ------------------------------------------------------------------
    def get_contact_panel_data(self):
        """Todo lo que necesita el panel lateral de la app para mostrar
        el contacto y sus últimos documentos, en una sola llamada."""
        self.ensure_one()
        partner = self.partner_id
        recent_orders = []
        recent_invoices = []
        if self.sale_installed and partner:
            orders = self.env['sale.order'].search(
                [('partner_id', '=', partner.id)], order='create_date desc', limit=5)
            recent_orders = [{
                'id': o.id,
                'name': o.name,
                'amount_total': o.amount_total,
                'state': o.state,
                'currency_symbol': o.currency_id.symbol,
            } for o in orders]
        if self.account_installed and partner:
            invoices = self.env['account.move'].search([
                ('partner_id', '=', partner.id),
                ('move_type', 'in', ('out_invoice', 'out_refund')),
            ], order='create_date desc', limit=5)
            recent_invoices = [{
                'id': i.id,
                'name': i.name or _("Borrador"),
                'amount_total': i.amount_total,
                'payment_state': i.payment_state,
                'state': i.state,
                'currency_symbol': i.currency_id.symbol,
            } for i in invoices]

        # 'credit' ("Total a cobrar") tiene groups= propio en el módulo
        # de Facturación: un agente que solo está en el grupo Chatroom
        # (sin acceso a Contabilidad) no lo puede leer directo. Se usa
        # sudo() solo para este campo puntual -es justamente el dato que
        # se quiere mostrarle al vendedor sin exigirle permisos de
        # Contabilidad, no una puerta trasera general del panel.
        partner_credit = partner.sudo().credit if self.account_installed and partner else 0.0

        activities = self._get_partner_activities()

        return {
            'has_partner': bool(partner),
            'partner_id': partner.id,
            # Para "romper" el caché del navegador en la URL del avatar
            # (/web/image/...) cuando se sube una foto nueva: sin esto,
            # el <img> sigue mostrando la respuesta vieja cacheada
            # aunque el campo haya cambiado. Mismo patrón que usa el
            # propio menú de usuario de Odoo (user_menu.js).
            'partner_write_date': partner.write_date,
            'name': partner.name or '',
            'phone': partner.phone or '',
            'email': partner.email or '',
            'company_name': partner.commercial_company_name or '',
            'city': partner.city or '',
            'country_name': partner.country_id.name or '',
            'assigned_user_id': self.assigned_user_id.id,
            'assigned_user_name': self.assigned_user_id.name or _("Sin asignar"),
            'assigned_user_initials': self.assigned_user_initials or '',
            'assigned_user_color': self.assigned_user_color,
            'crm_installed': self.crm_installed,
            'lead_count': self.lead_count,
            'sale_installed': self.sale_installed,
            'sale_order_count': self.sale_order_count,
            'purchase_installed': self.purchase_installed,
            'purchase_order_count': self.purchase_order_count,
            'account_installed': self.account_installed,
            'invoice_count': self.invoice_count,
            'project_installed': self.project_installed,
            'task_count': self.task_count,
            'product_installed': 'product.product' in self.env,
            'recent_orders': recent_orders,
            'recent_invoices': recent_invoices,
            'ai_paused': self.ai_paused,
            'cart_lines': [{
                'id': line.id,
                'product_name': line.product_name,
                'quantity': line.quantity,
                'price_unit': line.price_unit,
                'subtotal': line.quantity * line.price_unit,
            } for line in self.cart_line_ids],
            'cart_total': self.cart_total,
            'currency_symbol': self.env.company.currency_id.symbol,
            'partner_credit': partner_credit,
            'activities': [{
                'id': a.id,
                'summary': a.summary or a.activity_type_id.name,
                'date_deadline': a.date_deadline,
                'is_overdue': a.date_deadline < fields.Date.context_today(self),
            } for a in activities],
        }

    @api.depends('partner_id', 'pinned_lead_id')
    def _compute_next_activity(self):
        today = fields.Date.context_today(self)
        for rec in self:
            activity = rec._get_partner_activities(limit=1)
            if not activity:
                rec.next_activity_id = False
                rec.next_activity_summary = False
                rec.next_activity_date_deadline = False
                rec.next_activity_overdue = False
                rec.next_activity_user_id = False
                continue
            rec.next_activity_id = activity.id
            rec.next_activity_summary = activity.summary or activity.activity_type_id.name
            rec.next_activity_date_deadline = activity.date_deadline
            rec.next_activity_overdue = activity.date_deadline < today
            rec.next_activity_user_id = activity.user_id

    def _get_partner_activities(self, limit=10):
        """Actividades pendientes del contacto: las que están puestas
        directo sobre la ficha del partner, más las de sus oportunidades
        de CRM (que es donde de verdad suele vivir el "llamar a fulano
        el jueves" en un flujo de ventas)."""
        self.ensure_one()
        partner = self.partner_id
        if not partner:
            return self.env['mail.activity']
        activities = self.env['mail.activity'].search([
            ('res_model', '=', 'res.partner'),
            ('res_id', '=', partner.id),
        ], order='date_deadline asc', limit=limit)
        if self.crm_installed:
            lead_ids = self.env['crm.lead'].search([('partner_id', '=', partner.id)]).ids
            if lead_ids:
                activities |= self.env['mail.activity'].search([
                    ('res_model', '=', 'crm.lead'),
                    ('res_id', 'in', lead_ids),
                ], order='date_deadline asc', limit=limit)
        return activities.sorted(
            key=lambda activity: (
                activity.date_deadline or fields.Date.to_date('9999-12-31'), activity.id)
        )[:limit]

    def _activity_target(self):
        self.ensure_one()
        if self.crm_installed and self.pinned_lead_id:
            lead = self.env['crm.lead'].browse(self.pinned_lead_id).exists()
            if lead:
                return 'crm.lead', lead.id
        if self.partner_id:
            return 'res.partner', self.partner_id.id
        return False, False

    def get_next_activity_data(self):
        self.ensure_one()
        activity = self._get_partner_activities(limit=1)
        if not activity:
            return False
        today = fields.Date.context_today(self)
        return {
            'id': activity.id,
            'summary': activity.summary or activity.activity_type_id.name,
            'date_deadline': fields.Date.to_string(activity.date_deadline),
            'overdue': activity.date_deadline < today,
            'user_id': activity.user_id.id,
            'user_name': activity.user_id.name,
        }

    def action_mark_next_activity_done(self, activity_id=False):
        self.ensure_one()
        activity = self.env['mail.activity'].browse(activity_id or self.next_activity_id).exists()
        if not activity or activity not in self._get_partner_activities(limit=50):
            raise UserError(_("La actividad ya no está disponible."))
        activity.action_done()
        return self.get_next_activity_data()

    def action_reschedule_next_activity(self, activity_id=False, date_deadline=False):
        self.ensure_one()
        activity = self.env['mail.activity'].browse(activity_id or self.next_activity_id).exists()
        if not activity or activity not in self._get_partner_activities(limit=50):
            raise UserError(_("No hay una actividad para reprogramar."))
        new_date = fields.Date.to_date(date_deadline) if date_deadline else fields.Date.add(
            fields.Date.context_today(self), days=1)
        activity.write({'date_deadline': new_date})
        return self.get_next_activity_data()

    def action_create_followup_activity(self, summary=False, date_deadline=False):
        self.ensure_one()
        model_name, res_id = self._activity_target()
        if not model_name:
            raise UserError(_("Esta conversación no tiene contacto para crear una actividad."))
        activity_type = self.env['mail.activity.type'].search(
            [('category', '=', 'default')], order='sequence, id', limit=1)
        if not activity_type:
            raise UserError(_("No hay tipos de actividad configurados en Odoo."))
        activity = self.env['mail.activity'].create({
            'activity_type_id': activity_type.id,
            'summary': summary or _("Seguimiento de WhatsApp"),
            'date_deadline': fields.Date.to_date(date_deadline) if date_deadline else fields.Date.add(
                fields.Date.context_today(self), days=1),
            'user_id': self.assigned_user_id.id or self.env.user.id,
            'res_model_id': self.env['ir.model']._get_id(model_name),
            'res_id': res_id,
        })
        return self.get_next_activity_data() or {'id': activity.id}

    def action_open_activity_schedule(self):
        """Open Odoo's native activity scheduling wizard over the chat."""
        self.ensure_one()
        model_name, res_id = self._activity_target()
        if not model_name:
            raise UserError(_("Esta conversacion no tiene contacto para crear una actividad."))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Programar actividad'),
            'res_model': 'mail.activity.schedule',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {
                'active_model': model_name,
                'active_ids': [res_id],
                'active_id': res_id,
            },
        }

    def action_open_calendar_meeting(self):
        """Open Odoo Calendar's native meeting form from the conversation."""
        self.ensure_one()
        if not self.calendar_installed:
            raise UserError(_("El módulo Calendario no está instalado."))
        model_name, res_id = self._activity_target()
        if not model_name:
            raise UserError(_("Esta conversación no tiene contacto para crear una reunión."))
        meeting_type = self.env.ref('mail.mail_activity_data_meeting', raise_if_not_found=False)
        attendees = self.partner_id | self.assigned_user_id.partner_id
        action = self.env['ir.actions.actions']._for_xml_id('calendar.action_calendar_event')
        action.update({
            'name': _('Reunión desde Chatroom'),
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {
                'default_name': _('Reunión con %s') % self.display_name,
                'default_partner_ids': [(6, 0, attendees.ids)],
                'default_user_id': self.assigned_user_id.id or self.env.user.id,
                'default_res_model': model_name,
                'default_res_id': res_id,
                'default_activity_type_id': meeting_type.id if meeting_type else False,
                'default_description': self.ai_summary or '',
                'active_model': model_name,
                'active_id': res_id,
            },
        })
        return action

    # ------------------------------------------------------------------
    # Catálogo de productos: buscar y mandar uno por WhatsApp (foto +
    # nombre + precio), para no tener que salir del chat a armar un
    # catálogo aparte.
    # ------------------------------------------------------------------
    @api.model
    def search_products(self, query):
        if 'product.product' not in self.env:
            return []
        domain = [('sale_ok', '=', True)]
        if query:
            domain.append(('name', 'ilike', query))
        products = self.env['product.product'].search(domain, limit=8)
        return [{
            'id': p.id,
            'name': p.display_name,
            'list_price': p.list_price,
            'has_image': bool(p.image_128),
        } for p in products]

    @api.model
    def action_view_products(self):
        return self._window_action(
            name=_("Catálogo de productos"), res_model='product.product',
            view_mode='kanban,list,form')

    def action_send_product(self, product_id):
        self.ensure_one()
        product = self.env['product.product'].browse(product_id)
        if not product.exists():
            raise UserError(_("El producto ya no existe."))
        currency = self.env.company.currency_id
        caption = _("%(name)s - %(price)s %(currency)s") % {
            'name': product.display_name,
            'price': f"{product.list_price:.2f}",
            'currency': currency.symbol,
        }
        attachments = []
        if product.image_1920:
            data = product.image_1920
            attachments.append({
                'name': f"{product.name}.jpg",
                'mimetype': 'image/jpeg',
                'data': data.decode() if isinstance(data, bytes) else data,
            })
        self.action_send_message(body=caption, attachments=attachments)
        return True

    def _send_report_as_message(self, report_xmlid, res_id, filename):
        """Genera el PDF de un reporte estándar de Odoo (presupuesto,
        factura...) y lo manda como adjunto por la misma conversación,
        reusando el envío de adjuntos que ya existe (respeta ventana de
        24h, opt-out, etc. porque pasa por action_send_message)."""
        self.ensure_one()
        if not res_id:
            raise UserError(_("No se encontró el documento para generar el PDF."))
        report = self.env.ref(report_xmlid, raise_if_not_found=False)
        if not report:
            raise UserError(_("El reporte PDF '%s' no está instalado.") % report_xmlid)
        wkhtml_state = self.env['ir.actions.report'].get_wkhtmltopdf_state()
        if wkhtml_state != 'ok':
            messages = {
                'install': _("Odoo no encuentra wkhtmltopdf. Instala la versión compatible en el servidor y reinicia Odoo."),
                'upgrade': _("La versión de wkhtmltopdf es demasiado antigua para generar PDFs de Odoo."),
                'workers': _("Odoo necesita al menos dos workers para generar PDFs con wkhtmltopdf."),
                'broken': _("wkhtmltopdf está instalado pero no responde correctamente."),
            }
            raise UserError(messages.get(
                wkhtml_state,
                _("El renderizador PDF de Odoo no está disponible (estado: %s).") % wkhtml_state,
            ))
        try:
            pdf_content, _report_type = self.env['ir.actions.report'].with_context(
                force_report_rendering=True)._render_qweb_pdf(
                    report_xmlid, res_ids=[res_id])
        except Exception as exc:
            _logger.exception("No se pudo generar el PDF %s para %s", report_xmlid, res_id)
            raise UserError(_("No se pudo generar el PDF: %s") % exc) from exc
        if not pdf_content:
            raise UserError(_("El reporte no generó contenido PDF."))
        self.action_send_message(attachments=[{
            'name': filename,
            'mimetype': 'application/pdf',
            'data': base64.b64encode(pdf_content).decode(),
        }])
        return True

    def action_send_sale_order_pdf(self, order_id):
        self.ensure_one()
        if not self.sale_installed:
            raise UserError(_("El módulo Ventas no está instalado."))
        order = self.env['sale.order'].browse(order_id)
        if not order.exists():
            raise UserError(_("El presupuesto ya no existe."))
        return self._send_report_as_message(
            'sale.action_report_saleorder', order.id, f"{order.name}.pdf")

    def action_send_invoice_pdf(self, invoice_id):
        self.ensure_one()
        if not self.account_installed:
            raise UserError(_("El módulo Contabilidad no está instalado."))
        invoice = self.env['account.move'].browse(invoice_id)
        if not invoice.exists():
            raise UserError(_("La factura ya no existe."))
        return self._send_report_as_message(
            'account.account_invoices', invoice.id, f"{invoice.name or invoice.id}.pdf")

    def action_close(self):
        self.write({'state': 'closed'})
        for channel in self:
            channel._maybe_send_csat_survey()

    @api.model
    def _cron_close_inactive_channels(self, days=7):
        """Cierra automáticamente conversaciones sin actividad reciente."""
        limit_date = fields.Datetime.subtract(fields.Datetime.now(), days=days)
        stale = self.search([
            ('state', 'in', ['open', 'pending']),
            ('last_message_date', '<', limit_date),
        ])
        stale.write({'state': 'closed'})

    # ------------------------------------------------------------------
    # Datos de demostración (uso manual desde Configuración, no se cargan
    # solos al instalar: usan números de teléfono reales que pasó el
    # usuario para poder probar la interfaz con contactos de verdad).
    # ------------------------------------------------------------------
    def _get_or_create_demo_product(self):
        """Reusa cualquier producto vendible que ya exista (típico en una
        base con datos de demo de Odoo) para no llenar el catálogo de
        productos de prueba; si no hay ninguno, crea uno mínimo."""
        if 'product.product' not in self.env:
            return self.env['product.product']
        product = self.env['product.product'].search([('sale_ok', '=', True)], limit=1)
        if product:
            return product
        try:
            return self.env['product.product'].create({
                'name': "Combo de inicio (demo)",
                'list_price': 49.0,
            })
        except Exception:  # noqa: BLE001 - la demo no debe romperse por esto
            _logger.exception("No se pudo crear un producto de demo")
            return self.env['product.product']

    def _create_demo_sales_data(self, partner, scenario):
        """Oportunidad/presupuesto/factura de ejemplo para poder probar el
        panel de contacto (contadores, "enviar PDF por WhatsApp") con
        datos reales. Nunca debe hacer fallar la generación de las
        conversaciones: si algo no aplica en esta base (diario contable
        sin configurar, etc.) se registra en el log y se sigue de largo."""
        if 'crm.lead' in self.env:
            try:
                self.env['crm.lead'].create({
                    'name': _("Oportunidad demo - %s") % partner.name,
                    'partner_id': partner.id,
                    'phone': partner.phone,
                })
            except Exception:  # noqa: BLE001
                _logger.exception("No se pudo crear la oportunidad de demo para %s", partner.name)

        if 'sale.order' not in self.env:
            return
        try:
            product = self._get_or_create_demo_product()
            order_vals = {'partner_id': partner.id}
            if product:
                order_vals['order_line'] = [(0, 0, {
                    'product_id': product.id,
                    'product_uom_qty': 2,
                })]
            order = self.env['sale.order'].create(order_vals)
            if scenario == 'invoice' and 'account.move' in self.env:
                order.action_confirm()
                order._create_invoices()
        except Exception:  # noqa: BLE001
            _logger.exception("No se pudieron crear los datos de venta de demo para %s", partner.name)

    @api.model
    def action_generate_demo_conversations(self):
        """Crea 2 conversaciones de ejemplo con historial realista para
        poder probar la interfaz (kanban, app, dashboard, no leídos...)
        sin esperar tráfico real de WhatsApp. Es idempotente: si el
        contacto ya tiene una conversación, no la toca ni la duplica."""
        now = fields.Datetime.now()

        def ago(**delta):
            return fields.Datetime.subtract(now, **delta)

        demo_conversations = [
            {
                'name': "Bryan Cando",
                'phone': "593996726902",
                'state': 'pending',
                'ai_intent': 'consulta',
                'demo_sales': 'quotation',
                'messages': [
                    ('inbound', ago(hours=2),
                     "Hola buenas! Vi la página en Instagram, ¿siguen "
                     "teniendo el producto que estaba en la promo?", 'read'),
                    ('outbound', ago(hours=1, minutes=55),
                     "¡Hola Bryan! Sí, todavía tenemos stock. ¿Cuál te interesa?", 'read'),
                    ('inbound', ago(hours=1, minutes=50),
                     "El combo de inicio, el de $49", 'read'),
                    ('outbound', ago(hours=1, minutes=40),
                     "Perfecto, ese está disponible. ¿Querés que te pase el "
                     "link de pago o coordinamos el envío primero?", 'read'),
                    ('inbound', ago(hours=1, minutes=35),
                     "Mejor coordinamos el envío, vivo en Quito norte", 'read'),
                    ('inbound', ago(minutes=5),
                     "¿Cuánto tardaría en llegar?", 'received'),
                ],
            },
            {
                'name': "Cynthia Molina",
                'phone': "593998249518",
                'state': 'open',
                'ai_intent': 'venta',
                'demo_sales': 'invoice',
                'messages': [
                    ('inbound', ago(days=1, hours=3),
                     "Buenas tardes, quería confirmar si mi pedido ya fue despachado", 'read'),
                    ('outbound', ago(days=1, hours=2, minutes=55),
                     "¡Hola Cynthia! Dejame revisar el número de seguimiento, un momento", 'read'),
                    ('outbound', ago(days=1, hours=2, minutes=40),
                     "Ya salió ayer por la tarde, deberías tenerlo mañana. "
                     "Te paso el número de guía: 1234567890", 'read'),
                    ('inbound', ago(days=1, hours=2, minutes=30),
                     "Genial, muchas gracias!", 'read'),
                ],
            },
        ]

        created_names = []
        skipped_names = []
        for conv in demo_conversations:
            digits = re.sub(r'\D', '', conv['phone'])
            existing = self.search([
                ('channel_type', '=', 'whatsapp'),
                ('external_id', '=', digits),
            ], limit=1)
            if existing:
                skipped_names.append(conv['name'])
                continue

            partner = self.env['res.partner']._find_by_whatsapp_number(digits)
            if not partner:
                partner = self.env['res.partner'].create({
                    'name': conv['name'],
                    'phone': f"+{digits}",
                    'whatsapp_id': digits,
                })
            elif not partner.whatsapp_id:
                partner.whatsapp_id = digits

            channel = self.create({
                'channel_type': 'whatsapp',
                'external_id': digits,
                'partner_id': partner.id,
                'state': conv['state'],
                'ai_intent': conv['ai_intent'],
                'assigned_user_id': self.env.user.id,
            })
            last_date = now
            for direction, date, body, state in conv['messages']:
                self.env['chatroom.message'].create({
                    'channel_id': channel.id,
                    'direction': direction,
                    'message_type': 'text',
                    'body': body,
                    'state': state,
                    'date': date,
                })
                last_date = date
            channel.last_message_date = last_date
            if conv.get('demo_sales'):
                self._create_demo_sales_data(partner, conv['demo_sales'])
            created_names.append(conv['name'])

        if created_names:
            message = _("Conversaciones de prueba creadas: %s.") % ", ".join(created_names)
        else:
            message = _("Nada para crear")
        if skipped_names:
            message += " " + _("Ya existían (sin tocar): %s.") % ", ".join(skipped_names)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Datos de demostración"),
                'message': message,
                'type': 'success' if created_names else 'warning',
                'next': {
                    'type': 'ir.actions.client',
                    'tag': 'chatroom_whatsapp.chatroom_app',
                },
            },
        }

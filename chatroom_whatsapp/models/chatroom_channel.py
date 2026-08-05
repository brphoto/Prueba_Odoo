# -*- coding: utf-8 -*-
import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ChatroomChannel(models.Model):
    """Una conversación (WhatsApp / Messenger / Instagram) con un contacto.

    Cada canal agrupa los mensajes intercambiados con un mismo número/ID de
    red social, de forma análoga a una bandeja de entrada tipo "chatroom".
    """
    _name = 'chatroom.channel'
    _description = "Conversación de Chatroom (WhatsApp / Redes Sociales)"
    _inherit = ['mail.thread']
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
    message_ids = fields.One2many(
        'chatroom.message', 'channel_id', string="Mensajes")
    message_count = fields.Integer(compute='_compute_message_stats')
    unread_count = fields.Integer(compute='_compute_message_stats')
    last_message_date = fields.Datetime(index=True)
    last_message_preview = fields.Char(compute='_compute_message_stats')
    ai_suggested_reply = fields.Text(string="Sugerencia de IA")
    company_id = fields.Many2one(
        'res.company', default=lambda self: self.env.company)

    _sql_constraints = [
        ('external_id_type_uniq', 'unique(external_id, channel_type, company_id)',
         "Ya existe una conversación abierta para este contacto en este canal."),
    ]

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
            rec.last_message_preview = (last.body or '')[:120] if last else ''

    # ------------------------------------------------------------------
    # Helpers de contacto / canal
    # ------------------------------------------------------------------
    @api.model
    def _find_or_create_from_webhook(self, channel_type, external_id, profile_name=None):
        """Busca el canal para un contacto; crea el res.partner y el canal
        si es la primera vez que escribe (creación automática de contactos)."""
        channel = self.search([
            ('channel_type', '=', channel_type),
            ('external_id', '=', external_id),
        ], limit=1)
        if channel:
            return channel

        partner = self.env['res.partner'].search(
            [('whatsapp_id', '=', external_id)], limit=1)
        if not partner:
            partner = self.env['res.partner'].create({
                'name': profile_name or external_id,
                'whatsapp_id': external_id,
                'phone': f"+{external_id}" if channel_type == 'whatsapp' else False,
            })

        return self.create({
            'channel_type': channel_type,
            'external_id': external_id,
            'partner_id': partner.id,
        })

    # ------------------------------------------------------------------
    # Envío de mensajes (API directa de Meta, sin proveedores externos)
    # ------------------------------------------------------------------
    def _get_meta_credentials(self):
        icp = self.env['ir.config_parameter'].sudo()
        token = icp.get_param('chatroom_whatsapp.access_token')
        phone_number_id = icp.get_param('chatroom_whatsapp.phone_number_id')
        api_version = icp.get_param('chatroom_whatsapp.graph_api_version', 'v20.0')
        if not token or not phone_number_id:
            raise UserError(_(
                "Configura el Token de acceso y el Phone Number ID en "
                "Ajustes > Chatroom WhatsApp antes de enviar mensajes."))
        return token, phone_number_id, api_version

    def action_send_text(self, body):
        """Envía un mensaje de texto directo al Graph API de Meta y guarda
        el registro saliente. Solo aplica a WhatsApp por ahora; Messenger e
        Instagram usan el mismo patrón sobre /me/messages."""
        self.ensure_one()
        if self.channel_type != 'whatsapp':
            raise UserError(_("El envío directo aún solo está implementado "
                               "para WhatsApp en este módulo base."))

        token, phone_number_id, api_version = self._get_meta_credentials()
        url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": self.external_id,
            "type": "text",
            "text": {"body": body},
        }
        headers = {"Authorization": f"Bearer {token}"}

        message = self.env['chatroom.message'].create({
            'channel_id': self.id,
            'direction': 'outbound',
            'message_type': 'text',
            'body': body,
            'state': 'sent',
            'date': fields.Datetime.now(),
        })

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=15)
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
        return message

    # ------------------------------------------------------------------
    # Sugerencia de respuesta con IA
    # ------------------------------------------------------------------
    def action_ai_suggest_reply(self):
        self.ensure_one()
        icp = self.env['ir.config_parameter'].sudo()
        if not icp.get_param('chatroom_whatsapp.ai_enabled'):
            raise UserError(_(
                "Activa 'Sugerencias con IA' en Ajustes > Chatroom WhatsApp."))

        api_url = icp.get_param('chatroom_whatsapp.ai_provider_url')
        api_key = icp.get_param('chatroom_whatsapp.ai_api_key')
        model = icp.get_param('chatroom_whatsapp.ai_model', 'gpt-4o-mini')
        if not api_url or not api_key:
            raise UserError(_(
                "Configura el endpoint y la API Key del proveedor de IA."))

        history = self.message_ids.sorted('date')[-10:]
        conversation = [
            {"role": "user" if m.direction == 'inbound' else "assistant",
             "content": m.body or ''}
            for m in history
        ]
        system_prompt = _(
            "Eres un asistente de atención al cliente por WhatsApp. "
            "Responde en español, de forma breve, cordial y orientada a "
            "avanzar la venta o resolver la consulta del cliente.")

        try:
            response = requests.post(
                api_url,
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [{"role": "system", "content": system_prompt}] + conversation,
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            suggestion = data["choices"][0]["message"]["content"]
        except (requests.RequestException, KeyError, IndexError) as exc:
            _logger.error("Error consultando IA: %s", exc)
            raise UserError(_("No se pudo obtener una sugerencia de IA: %s") % exc)

        self.ai_suggested_reply = suggestion
        return True

    def action_send_ai_suggestion(self):
        self.ensure_one()
        if not self.ai_suggested_reply:
            raise UserError(_("No hay ninguna sugerencia de IA generada."))
        self.action_send_text(self.ai_suggested_reply)
        self.ai_suggested_reply = False
        return True

    # ------------------------------------------------------------------
    # Flujo comercial: crear oportunidad / presupuesto desde la conversación
    # ------------------------------------------------------------------
    def action_create_lead(self):
        self.ensure_one()
        if 'crm.lead' not in self.env:
            raise UserError(_("El módulo CRM no está instalado."))
        lead = self.env['crm.lead'].create({
            'name': _("Oportunidad WhatsApp - %s") % (self.partner_id.name or self.external_id),
            'partner_id': self.partner_id.id,
            'phone': self.partner_id.phone,
            'description': "\n".join(
                f"[{m.direction}] {m.body}" for m in self.message_ids.sorted('date')),
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'crm.lead',
            'res_id': lead.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_create_quotation(self):
        self.ensure_one()
        if 'sale.order' not in self.env:
            raise UserError(_("El módulo Ventas no está instalado."))
        if not self.partner_id:
            raise UserError(_("La conversación no tiene un contacto asociado."))
        order = self.env['sale.order'].create({
            'partner_id': self.partner_id.id,
            'origin': self.display_name,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': order.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_close(self):
        self.write({'state': 'closed'})

    @api.model
    def _cron_close_inactive_channels(self, days=7):
        """Cierra automáticamente conversaciones sin actividad reciente."""
        limit_date = fields.Datetime.subtract(fields.Datetime.now(), days=days)
        stale = self.search([
            ('state', 'in', ['open', 'pending']),
            ('last_message_date', '<', limit_date),
        ])
        stale.write({'state': 'closed'})

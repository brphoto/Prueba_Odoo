# -*- coding: utf-8 -*-
import base64
import json
import logging
import mimetypes

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
    ai_intent = fields.Selection(
        [('consulta', "Consulta"),
         ('venta', "Venta"),
         ('soporte', "Soporte"),
         ('queja', "Queja"),
         ('otro', "Otro")],
        string="Intención (IA)", tracking=True)
    company_id = fields.Many2one(
        'res.company', default=lambda self: self.env.company)

    pinned_lead_id = fields.Many2one(
        'crm.lead', string="Oportunidad vinculada",
        domain="[('partner_id', '=', partner_id)]")
    crm_installed = fields.Boolean(compute='_compute_related_counts')
    sale_installed = fields.Boolean(compute='_compute_related_counts')
    account_installed = fields.Boolean(compute='_compute_related_counts')
    lead_count = fields.Integer(compute='_compute_related_counts')
    sale_order_count = fields.Integer(compute='_compute_related_counts')
    invoice_count = fields.Integer(compute='_compute_related_counts')

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

    def _compute_related_counts(self):
        crm_installed = 'crm.lead' in self.env
        sale_installed = 'sale.order' in self.env
        account_installed = 'account.move' in self.env
        for rec in self:
            rec.crm_installed = crm_installed
            rec.sale_installed = sale_installed
            rec.account_installed = account_installed
            partner = rec.partner_id
            rec.lead_count = (
                self.env['crm.lead'].search_count([('partner_id', '=', partner.id)])
                if crm_installed and partner else 0)
            rec.sale_order_count = (
                self.env['sale.order'].search_count([('partner_id', '=', partner.id)])
                if sale_installed and partner else 0)
            rec.invoice_count = (
                self.env['account.move'].search_count([
                    ('partner_id', '=', partner.id),
                    ('move_type', 'in', ('out_invoice', 'out_refund')),
                ]) if account_installed and partner else 0)

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
        response = requests.post(
            url, headers={"Authorization": f"Bearer {token}"},
            data={'messaging_product': 'whatsapp'}, files=files, timeout=60)
        response.raise_for_status()
        return response.json()['id']

    def action_send_message(self, body=False, attachments=None):
        """Punto de entrada único usado por la interfaz de chat: envía
        texto y/o uno o varios archivos adjuntos (arrastrados o
        seleccionados) en la misma conversación.

        :param attachments: lista de dicts {name, mimetype, data(base64)}
        """
        self.ensure_one()
        if self.channel_type != 'whatsapp':
            raise UserError(_("El envío directo aún solo está implementado "
                               "para WhatsApp en este módulo base."))
        attachments = attachments or []
        if not attachments:
            if not body:
                raise UserError(_("Escribe un mensaje o adjunta un archivo."))
            return self.action_send_text(body)

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

            message = self.env['chatroom.message'].create({
                'channel_id': self.id,
                'direction': 'outbound',
                'message_type': media_type,
                'body': caption,
                'state': 'sent',
                'date': fields.Datetime.now(),
                'attachment_ids': [(4, attachment.id)],
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
                response = requests.post(url, json=payload, headers=headers, timeout=60)
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

    def _notify_thread_update(self):
        """Notifica por el bus a quien tenga abierta la conversación para
        refrescar el chat en tiempo real, sin recargar la página."""
        for rec in self:
            self.env['bus.bus']._sendone(
                f'chatroom_channel_{rec.id}', 'chatroom.message/new',
                {'channel_id': rec.id})

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
        response = requests.post(
            api_url,
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

    def _ai_process_inbound_message(self, message):
        """Automatizaciones opcionales al recibir un mensaje: clasificar
        la intención, crear una oportunidad automáticamente si aplica y/o
        responder de forma autónoma. Se activan por separado en Ajustes;
        cualquier fallo se registra en el log sin interrumpir el webhook."""
        self.ensure_one()
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
    def action_create_lead(self):
        self.ensure_one()
        if not self.crm_installed:
            raise UserError(_("El módulo CRM no está instalado."))
        lead = self.env['crm.lead'].create({
            'name': _("Oportunidad WhatsApp - %s") % (self.partner_id.name or self.external_id),
            'partner_id': self.partner_id.id,
            'phone': self.partner_id.phone,
            'description': "\n".join(
                f"[{m.direction}] {m.body}" for m in self.message_ids.sorted('date') if m.body),
        })
        self.pinned_lead_id = lead.id
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'crm.lead',
            'res_id': lead.id,
            'view_mode': 'form',
            'target': 'current',
        }

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
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': order.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_leads(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Oportunidades"),
            'res_model': 'crm.lead',
            'view_mode': 'list,kanban,form',
            'domain': [('partner_id', '=', self.partner_id.id)],
            'context': {'default_partner_id': self.partner_id.id},
        }

    def action_view_sale_orders(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Presupuestos y Pedidos"),
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'domain': [('partner_id', '=', self.partner_id.id)],
            'context': {'default_partner_id': self.partner_id.id},
        }

    def action_view_invoices(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Facturas"),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [
                ('partner_id', '=', self.partner_id.id),
                ('move_type', 'in', ('out_invoice', 'out_refund')),
            ],
            'context': {'default_partner_id': self.partner_id.id, 'default_move_type': 'out_invoice'},
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

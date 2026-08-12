# -*- coding: utf-8 -*-
import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ChatroomWhatsappNumber(models.Model):
    """Una línea de WhatsApp Business (ej. 'Ventas', 'Soporte').

    Permite operar varios números de WhatsApp desde el mismo Odoo: cada
    línea tiene su propio Phone Number ID (y, opcionalmente, su propio
    token) y un equipo de agentes. El webhook identifica por qué número
    entró cada mensaje (`metadata.phone_number_id` en el payload de Meta)
    y asigna la conversación a la línea correspondiente.
    """
    _name = 'chatroom.whatsapp.number'
    _description = "Línea de WhatsApp Business"
    _order = 'sequence, name'
    # mail.thread solo para poder avisarle a los administradores cuando
    # baja la calidad de la línea (message_post con partner_ids), sin
    # infraestructura de notificaciones aparte; no se agregó <chatter/>
    # a la vista porque no hace falta un historial completo, solo el
    # aviso puntual.
    _inherit = ['chatroom.meta.mixin', 'mail.thread']

    name = fields.Char(required=True, help="Nombre interno, ej. 'Ventas', 'Soporte Ecuador'.")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    color = fields.Integer(string="Color")

    phone_number_id = fields.Char(
        string="Phone Number ID", required=True,
        help="Phone Number ID de esta línea en Meta Business Suite > "
             "WhatsApp > Configuración de la API.")
    display_phone_number = fields.Char(
        string="Número (referencia)",
        help="Solo informativo, para reconocer la línea de un vistazo "
             "(ej. '+593 99 123 4567'). No se usa para enviar mensajes.")
    access_token = fields.Char(
        string="Token de acceso (si es distinto del general)",
        groups="chatroom_whatsapp.group_chatroom_manager",
        help="Dejalo vacío si todas tus líneas comparten el mismo System "
             "User / token permanente configurado en Ajustes. Completalo "
             "solo si esta línea vive en otra WhatsApp Business Account "
             "con su propio token.")
    business_account_id = fields.Char(string="WhatsApp Business Account ID (WABA)")

    member_ids = fields.Many2many(
        'res.users', 'chatroom_whatsapp_number_user_rel', 'number_id', 'user_id',
        string="Agentes de esta línea",
        help="Si está vacío, cualquier agente del grupo Chatroom puede "
             "atenderla y entra en el reparto automático general. Si "
             "tiene agentes, las conversaciones nuevas de esta línea se "
             "reparten solo entre ellos.")

    channel_count = fields.Integer(compute='_compute_channel_count')
    last_quality_rating = fields.Char(
        string="Última calidad conocida", copy=False, readonly=True,
        help="GREEN/YELLOW/RED/UNKNOWN, tal como lo devuelve la Graph "
             "API. Se actualiza al probar la conexión (a mano) o solo, "
             "una vez por día, con el chequeo automático de calidad.")

    _phone_number_id_uniq = models.Constraint(
        'unique(phone_number_id)',
        "Ya existe una línea configurada con ese Phone Number ID.",
    )

    def _compute_channel_count(self):
        counts = dict(self.env['chatroom.channel']._read_group(
            [('whatsapp_number_id', 'in', self.ids)],
            ['whatsapp_number_id'], ['__count']))
        for rec in self:
            rec.channel_count = counts.get(rec, 0)

    def action_view_channels(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': 'chatroom.channel',
            'view_mode': 'list,kanban,form',
            'views': [(False, 'list'), (False, 'kanban'), (False, 'form')],
            'domain': [('whatsapp_number_id', '=', self.id)],
        }

    def _get_credentials(self):
        """Token + Phone Number ID a usar para enviar por esta línea
        específica: el token propio si se configuró, o si no el token
        general (caso típico: una sola WABA con varios números)."""
        self.ensure_one()
        icp = self.env['ir.config_parameter'].sudo()
        token = self.access_token or icp.get_param('chatroom_whatsapp.access_token')
        api_version = icp.get_param('chatroom_whatsapp.graph_api_version', 'v20.0')
        if not token or not self.phone_number_id:
            raise UserError(_(
                "Falta el token de acceso o el Phone Number ID de la "
                "línea '%s'.") % self.name)
        return token, self.phone_number_id, api_version

    def _fetch_phone_info(self):
        """Consulta la Graph API por nombre verificado, número y calidad
        de esta línea. Compartido entre el botón manual "Probar
        conexión" y el chequeo automático de calidad, para no tener el
        mismo llamado a Meta escrito dos veces."""
        self.ensure_one()
        token, phone_number_id, api_version = self._get_credentials()
        url = f"https://graph.facebook.com/{api_version}/{phone_number_id}"
        try:
            response = self._meta_request(
                'GET', url,
                params={'fields': 'display_phone_number,verified_name,quality_rating'},
                headers={"Authorization": f"Bearer {token}"},
                timeout=15, max_retries=0,
            )
            data = response.json()
            if response.status_code >= 400:
                error = data.get('error', {}).get('message', str(data))
                raise UserError(_("Meta respondió con un error: %s") % error)
        except requests.RequestException as exc:
            _logger.error("Error consultando la línea %s: %s", self.name, exc)
            raise UserError(_("No se pudo conectar con Meta: %s") % exc)
        return data

    def action_test_connection(self):
        """Igual que el botón general de Ajustes pero con las
        credenciales propias de esta línea (si las tiene)."""
        self.ensure_one()
        data = self._fetch_phone_info()
        new_rating = (data.get('quality_rating') or '').upper() or False
        if new_rating:
            self.last_quality_rating = new_rating
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Conexión OK"),
                'message': _("Número verificado: %(name)s (%(phone)s). Calidad: %(quality)s.") % {
                    'name': data.get('verified_name') or '?',
                    'phone': data.get('display_phone_number') or self.phone_number_id,
                    'quality': data.get('quality_rating') or '?',
                },
                'type': 'success',
            },
        }

    # ------------------------------------------------------------------
    # Chequeo automático de calidad: la calidad de un número es el
    # activo más caro de todo este sistema -si Meta la baja a amarillo o
    # rojo puede terminar restringiendo o baneando el número, cortando
    # toda la operación. El botón "Probar conexión" ya mostraba la
    # calidad, pero solo si alguien se acordaba de mirarlo a mano.
    # ------------------------------------------------------------------
    _QUALITY_RANK = {'RED': 0, 'YELLOW': 1, 'GREEN': 2}

    def _check_quality_rating(self):
        """Compara la calidad actual contra la última conocida; si
        empeoró, avisa a los administradores. Nunca hace ruido en el
        primer chequeo (no hay "antes" con qué comparar) ni cuando la
        calidad mejora o se mantiene igual."""
        self.ensure_one()
        try:
            data = self._fetch_phone_info()
        except UserError as exc:
            _logger.info(
                "No se pudo revisar la calidad de la línea %s: %s", self.name, exc)
            return
        new_rating = (data.get('quality_rating') or '').upper()
        old_rating = self.last_quality_rating
        old_rank = self._QUALITY_RANK.get(old_rating)
        new_rank = self._QUALITY_RANK.get(new_rating)
        if old_rank is not None and new_rank is not None and new_rank < old_rank:
            self._notify_quality_drop(old_rating, new_rating)
        if new_rating:
            self.last_quality_rating = new_rating

    def _notify_quality_drop(self, old_rating, new_rating):
        self.ensure_one()
        managers = self.env.ref(
            'chatroom_whatsapp.group_chatroom_manager', raise_if_not_found=False)
        partner_ids = managers.user_ids.mapped('partner_id').ids if managers else []
        if not partner_ids:
            return
        self.message_post(
            body=_(
                "⚠️ La calidad de la línea de WhatsApp \"%(name)s\" bajó de "
                "%(old)s a %(new)s. Meta puede restringir o banear números "
                "con calidad baja: conviene revisar las plantillas y los "
                "mensajes recientes, y el feedback/bloqueos de clientes."
            ) % {'name': self.name, 'old': old_rating, 'new': new_rating},
            partner_ids=partner_ids,
            subtype_xmlid='mail.mt_comment',
        )

    @api.model
    def _cron_check_quality_ratings(self):
        for number in self.search([('active', '=', True)]):
            number._check_quality_rating()

    def _get_next_assignee(self):
        """Reparte entre los agentes de esta línea si tiene (member_ids);
        si está vacía, delega en el reparto general de todos los agentes."""
        self.ensure_one()
        return self.env['chatroom.channel']._get_next_assignee(self.member_ids or None)

    @api.model
    def _find_by_phone_number_id(self, phone_number_id):
        if not phone_number_id:
            return self.browse()
        return self.search([('phone_number_id', '=', phone_number_id)], limit=1)

# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


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
    _inherit = ['chatroom.meta.mixin']

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

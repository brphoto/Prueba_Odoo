# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    rfm_score = fields.Integer(related='partner_id.rfm_score', readonly=True)
    rfm_category = fields.Selection(related='partner_id.rfm_category', readonly=True)
    commercial_total_sales = fields.Monetary(
        related='partner_id.commercial_total_sales', readonly=True,
        # crm.lead usa 'company_currency' como currency_field propio
        # (no tiene 'currency_id'): sin esto, el campo Monetary no
        # encuentra dónde resolver la moneda y falla al cargar.
        currency_field='company_currency')
    commercial_last_sale_date = fields.Date(
        related='partner_id.commercial_last_sale_date', readonly=True)

    chatroom_channel_count = fields.Integer(compute='_compute_chatroom_channel_data')
    chatroom_last_message_preview = fields.Char(compute='_compute_chatroom_channel_data')
    chatroom_last_message_date = fields.Datetime(compute='_compute_chatroom_channel_data')
    sla_timer = fields.Datetime(
        string="Temporizador SLA", copy=False, index=True,
        help="Fecha límite para que el asesor responda antes de liberar la oportunidad al pool.")
    assignment_pool_status = fields.Selection([
        ('assigned', 'Asignada'), ('pool', 'Sin asignar / Pool'),
    ], string="Estado de asignación", default='assigned', copy=False, index=True)

    @api.model
    def _lead_sla_deadline(self):
        try:
            hours = max(1, int(self.env['ir.config_parameter'].sudo().get_param(
                'chatroom_sales_intelligence.lead_sla_hours', 2)))
        except (TypeError, ValueError):
            hours = 2
        return fields.Datetime.add(fields.Datetime.now(), hours=hours)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.setdefault('sla_timer', self._lead_sla_deadline())
            vals.setdefault('assignment_pool_status', 'assigned' if vals.get('user_id') else 'pool')
        return super().create(vals_list)

    def write(self, vals):
        vals = dict(vals)
        if any(field in vals for field in ('stage_id', 'user_id', 'activity_ids')):
            vals.setdefault('sla_timer', self._lead_sla_deadline())
        if 'user_id' in vals:
            vals.setdefault('assignment_pool_status', 'assigned' if vals['user_id'] else 'pool')
        result = super().write(vals)
        if 'stage_id' in vals:
            self.env['chat.automation.rule']._run_for_leads(self, 'stage_change')
        if 'tag_ids' in vals:
            self.env['chat.automation.rule']._run_for_leads(self, 'tag_added')
        return result

    @api.model
    def _cron_process_lead_sla(self):
        now = fields.Datetime.now()
        leads = self.search([
            ('active', '=', True), ('user_id', '!=', False),
            ('sla_timer', '!=', False), ('sla_timer', '<=', now),
            ('probability', '<', 100),
        ])
        Activity = self.env['mail.activity']
        PoolTag = self.env['crm.tag'] if 'crm.tag' in self.env else False
        pool_tag = PoolTag.search([('name', '=', 'Sin asignar / Pool')], limit=1) if PoolTag else False
        for lead in leads:
            pending = Activity.search_count([
                ('res_model', '=', 'crm.lead'), ('res_id', '=', lead.id),
            ])
            if pending:
                continue
            vals = {
                'user_id': False,
                'assignment_pool_status': 'pool',
                'sla_timer': False,
            }
            if pool_tag and pool_tag not in lead.tag_ids:
                vals['tag_ids'] = [(4, pool_tag.id)]
            lead.write(vals)
            lead.message_post(body=_(
                "La oportunidad fue liberada al pool por vencimiento del SLA sin actividad hecha."))
        return len(leads)

    def _get_chatroom_channels(self):
        """Todas las conversaciones de WhatsApp/Messenger/Instagram del
        contacto de esta oportunidad, más recientes primero. Se busca
        por partner_id (no hay un vínculo directo oportunidad->canal:
        el vínculo inverso ya existe, chatroom.channel.pinned_lead_id,
        pero es opcional y una conversación puede no tener ninguna
        oportunidad anclada todavía)."""
        self.ensure_one()
        if not self.partner_id:
            return self.env['chatroom.channel']
        return self.env['chatroom.channel'].search(
            [('partner_id', '=', self.partner_id.id)], order='last_message_date desc')

    def _compute_chatroom_channel_data(self):
        for lead in self:
            channels = lead._get_chatroom_channels()
            lead.chatroom_channel_count = len(channels)
            latest = channels[:1]
            lead.chatroom_last_message_preview = latest.last_message_preview if latest else False
            lead.chatroom_last_message_date = latest.last_message_date if latest else False

    def action_view_chatroom_channels(self):
        """Botón inteligente 'WhatsApp': con una sola conversación, la
        abre directo en su formulario como diálogo -funciona bien porque
        es una sola vista (a diferencia de un diálogo multi-vista tipo
        lista+form, que el framework no deja navegar adentro: ver la
        nota sobre switchView() en el README de chatroom_whatsapp). Con
        varias, abre la lista clásica navegando (sin forzar diálogo),
        que es el comportamiento estándar de cualquier smart button de
        Odoo y no tiene ese problema."""
        self.ensure_one()
        if not self.partner_id:
            raise UserError(_("Esta oportunidad no tiene un contacto asociado."))
        channels = self._get_chatroom_channels()
        if not channels:
            raise UserError(_(
                "%s todavía no tiene ninguna conversación de WhatsApp.") % self.partner_id.name)
        if len(channels) == 1:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'chatroom.channel',
                'res_id': channels.id,
                'views': [(False, 'form')],
                'target': 'new',
            }
        return {
            'type': 'ir.actions.act_window',
            'name': _("Conversaciones de WhatsApp"),
            'res_model': 'chatroom.channel',
            'views': [(False, 'list'), (False, 'kanban'), (False, 'form')],
            'domain': [('partner_id', '=', self.partner_id.id)],
        }

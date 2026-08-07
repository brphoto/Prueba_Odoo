# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError


class ChatroomChannel(models.Model):
    _inherit = 'chatroom.channel'

    rfm_category = fields.Selection(related='partner_id.rfm_category', readonly=True)
    management_alert_state = fields.Selection(
        [('green', "Verde"), ('yellow', "Amarillo"), ('red', "Rojo")],
        compute='_compute_management_alert')
    management_days_stagnant = fields.Integer(compute='_compute_management_alert')

    def _get_relevant_lead(self):
        """La oportunidad a usar para el semáforo de seguimiento: la
        anclada a la conversación si existe y sigue abierta; si no, la
        oportunidad abierta más reciente del contacto."""
        self.ensure_one()
        lead = self.env['crm.lead']
        if self.pinned_lead_id:
            candidate = self.env['crm.lead'].browse(self.pinned_lead_id).exists()
            if candidate and candidate.active and not candidate.stage_id.is_won:
                lead = candidate
        if not lead and self.partner_id:
            lead = self.env['crm.lead'].search([
                ('partner_id', '=', self.partner_id.id),
                ('active', '=', True),
                ('stage_id.is_won', '=', False),
            ], order='date_last_stage_update desc', limit=1)
        return lead

    def _compute_management_alert(self):
        for rec in self:
            lead = rec._get_relevant_lead()
            rec.management_alert_state = lead.management_alert_state if lead else 'green'
            rec.management_days_stagnant = lead.days_since_last_management if lead else 0

    def get_commercial_intelligence(self):
        """Paquete de datos para el panel lateral deslizable: se arma en
        un solo método/una sola llamada RPC para no encadenar varias
        peticiones desde el cliente cada vez que se abre el panel."""
        self.ensure_one()
        partner = self.partner_id
        if not partner:
            return {'has_partner': False}

        lead = self._get_relevant_lead()
        currency = partner.currency_id

        return {
            'has_partner': True,
            'partner_name': partner.name,
            'rfm_category': partner.rfm_category,
            'rfm_category_label': dict(
                partner._fields['rfm_category'].selection).get(partner.rfm_category),
            'rfm_score': partner.rfm_score,
            'lead_id': lead.id if lead else False,
            'lead_name': lead.name if lead else False,
            'lead_create_date': fields.Datetime.to_string(lead.create_date) if lead else False,
            'days_since_last_management': lead.days_since_last_management if lead else False,
            'management_alert_state': lead.management_alert_state if lead else 'green',
            'commercial_total_sales': partner.commercial_total_sales,
            'commercial_invoice_count': partner.commercial_invoice_count,
            'commercial_avg_ticket': partner.commercial_avg_ticket,
            'commercial_last_sale_date': fields.Date.to_string(partner.commercial_last_sale_date)
                if partner.commercial_last_sale_date else False,
            'currency_symbol': currency.symbol,
            'currency_position': currency.position,
            'top_products': partner._get_top_products(limit=5),
        }

    def action_ai_generate_followup(self):
        """Genera con IA un mensaje corto de seguimiento para una
        oportunidad estancada, usando el mismo proveedor configurado para
        las sugerencias de respuesta del chatroom base."""
        self.ensure_one()
        lead = self._get_relevant_lead()
        system_prompt = _(
            "Eres un asistente de ventas. Redacta en español un mensaje "
            "corto y cordial de WhatsApp para retomar el contacto con un "
            "cliente cuya oportunidad de venta lleva %(days)s días sin "
            "gestión. Menciona el producto o motivo de interés si aparece "
            "en la conversación. No uses saludos genéricos largos ni "
            "firmes el mensaje."
        ) % {'days': lead.days_since_last_management if lead else '?'}
        try:
            suggestion = self._ai_chat_completion(
                self._ai_build_conversation(extra_system=system_prompt))
        except UserError:
            raise
        except Exception as exc:  # noqa: BLE001 - cualquier error de IA se informa, no rompe la UI
            raise UserError(_("No se pudo generar el mensaje de seguimiento: %s") % exc)
        self.ai_suggested_reply = suggestion
        return suggestion

# -*- coding: utf-8 -*-
from odoo import api, fields, models

RED_THRESHOLD_DAYS = 15
YELLOW_THRESHOLD_DAYS = 7


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    days_since_last_management = fields.Integer(
        string="Días sin gestión", compute='_compute_management_alert')
    management_alert_state = fields.Selection(
        [('green', "Verde"), ('yellow', "Amarillo"), ('red', "Rojo")],
        string="Alerta de seguimiento", compute='_compute_management_alert')

    def _get_last_management_date(self):
        """Última fecha de 'gestión' real de la oportunidad: la más
        reciente entre el cambio de etapa (date_last_stage_update, nativo
        de Odoo), el último mensaje/nota del chatter y la última
        actividad registrada (aunque no esté cerrada).

        Solo cuentan los mensajes que un humano generó a propósito
        (nota, comentario, correo): las notificaciones automáticas del
        sistema (creación del registro, cambios de seguimiento) no son
        "gestión" y no deben tapar una oportunidad realmente estancada."""
        self.ensure_one()
        candidates = [self.date_last_stage_update or self.create_date]
        human_messages = self.message_ids.filtered(
            lambda m: m.message_type in ('comment', 'email', 'email_outgoing'))
        last_message = human_messages.sorted('date', reverse=True)[:1]
        if last_message:
            candidates.append(last_message.date)
        last_activity = self.activity_ids.sorted('create_date', reverse=True)[:1]
        if last_activity:
            candidates.append(last_activity.create_date)
        return max(c for c in candidates if c)

    @api.depends('date_last_stage_update', 'message_ids.date', 'activity_ids.create_date',
                 'active', 'stage_id.is_won')
    def _compute_management_alert(self):
        now = fields.Datetime.now()
        for lead in self:
            if not lead.active or lead.stage_id.is_won:
                # Perdida (archivada) o ganada: ya no aplica el semáforo de
                # seguimiento. OJO: no se puede usar 'probability == 0' para
                # esto, un lead recién creado y todavía sin calificar
                # también tiene probability 0 sin estar perdido.
                lead.days_since_last_management = 0
                lead.management_alert_state = 'green'
                continue
            last_date = lead._get_last_management_date()
            days = (now - last_date).days if last_date else 0
            lead.days_since_last_management = days
            if days > RED_THRESHOLD_DAYS:
                lead.management_alert_state = 'red'
            elif days > YELLOW_THRESHOLD_DAYS:
                lead.management_alert_state = 'yellow'
            else:
                lead.management_alert_state = 'green'

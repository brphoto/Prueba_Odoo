from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.marketing_command_center.models.marketing_social_constants import PLATFORM_LABELS


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    marketing_account_id = fields.Many2one(
        'marketing.social.account', string='Cuenta social de origen',
        ondelete='set null', index=True, tracking=True)
    marketing_publication_id = fields.Many2one(
        'marketing.social.publication', string='Publicación de origen',
        ondelete='set null', index=True, tracking=True)
    marketing_campaign_id = fields.Many2one(
        'marketing.social.campaign', string='Campaña de origen',
        ondelete='set null', index=True, tracking=True)
    marketing_conversation_id = fields.Many2one(
        'marketing.social.conversation', string='Conversación de origen',
        ondelete='set null', index=True, tracking=True)
    marketing_platform = fields.Selection(
        related='marketing_account_id.platform', string='Red de origen',
        store=True, readonly=True)
    marketing_last_message_at = fields.Datetime(
        related='marketing_conversation_id.last_message_at',
        string='Último mensaje social', readonly=True)
    marketing_message_count = fields.Integer(
        compute='_compute_marketing_profile', string='Mensajes sociales')
    marketing_interaction_count = fields.Integer(
        compute='_compute_marketing_profile', string='Interacciones sociales')
    marketing_quality_score = fields.Integer(
        compute='_compute_marketing_profile', string='Calidad del lead (%)')
    marketing_quality_status = fields.Selection([
        ('new', 'Por completar'), ('qualified', 'Bien perfilado'),
        ('excellent', 'Alta calidad'),
    ], compute='_compute_marketing_profile', string='Estado de calidad')
    marketing_rfm_segment = fields.Selection([
        ('a', 'A - Alto valor'), ('b', 'B - Valor medio'),
        ('c', 'C - Bajo valor'), ('manual', 'Manual'),
    ], string='Segmento RFM / ABC', tracking=True)
    marketing_next_action = fields.Selection([
        ('contact', 'Contactar'), ('quote', 'Preparar cotización'),
        ('meeting', 'Agendar reunión'), ('nurture', 'Nutrir relación'),
        ('close', 'Cerrar seguimiento'),
    ], string='Siguiente acción comercial', tracking=True)
    marketing_qualification_notes = fields.Text(
        string='Notas de calificación',
        help='Contexto que ayuda al equipo a decidir el siguiente paso.')
    marketing_attribution_note = fields.Char(
        string='Resumen de atribución', compute='_compute_marketing_profile')

    @api.depends(
        'partner_id', 'email_from', 'phone', 'user_id',
        'expected_revenue', 'marketing_account_id',
        'marketing_publication_id', 'marketing_campaign_id',
        'marketing_conversation_id', 'marketing_conversation_id.message_ids',
        'marketing_publication_id.interaction_ids',
    )
    def _compute_marketing_profile(self):
        for lead in self:
            conversation = lead.marketing_conversation_id
            publication = lead.marketing_publication_id
            score = 0
            score += 20 if lead.partner_id else 0
            score += 15 if lead.email_from else 0
            score += 15 if (lead.phone or (lead.partner_id and lead.partner_id.mobile)) else 0
            score += 15 if lead.user_id else 0
            score += 15 if conversation else 0
            score += 10 if publication else 0
            score += 10 if lead.expected_revenue else 0
            lead.marketing_quality_score = min(score, 100)
            lead.marketing_quality_status = (
                'excellent' if score >= 80 else
                'qualified' if score >= 50 else 'new')
            lead.marketing_message_count = len(conversation.message_ids) if conversation else 0
            lead.marketing_interaction_count = len(publication.interaction_ids) if publication else 0
            bits = []
            if lead.marketing_platform:
                bits.append(PLATFORM_LABELS.get(lead.marketing_platform, lead.marketing_platform))
            if publication:
                bits.append(publication.name)
            if lead.marketing_campaign_id:
                bits.append(lead.marketing_campaign_id.name)
            lead.marketing_attribution_note = ' · '.join(bits) or _('Origen no atribuido')

    def action_open_marketing_conversation(self):
        self.ensure_one()
        if not self.marketing_conversation_id:
            raise UserError(_('Este lead todavía no tiene una conversación social vinculada.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Conversación de %s') % self.name,
            'res_model': 'marketing.social.conversation',
            'res_id': self.marketing_conversation_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_schedule_marketing_followup(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Programar seguimiento'),
            'res_model': 'mail.activity.schedule',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_res_model': self._name,
                'default_res_ids': self.ids,
                'default_note': self.marketing_qualification_notes or '',
            },
        }

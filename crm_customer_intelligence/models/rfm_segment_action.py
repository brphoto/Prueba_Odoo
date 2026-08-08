# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class RfmSegmentAction(models.Model):
    _name = 'crm.rfm.segment.action'
    _description = 'Acción automática de segmento RFM'
    _order = 'sequence, id'

    segment_id = fields.Many2one('crm.rfm.segment', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    action_type = fields.Selection([
        ('activity', 'Crear actividad de Odoo'),
        ('tag', 'Agregar etiqueta al contacto'),
        ('assign_user', 'Asignar oportunidades a un vendedor'),
        ('lead_stage', 'Cambiar etapa de oportunidades'),
        ('whatsapp_template', 'Enviar plantilla de WhatsApp'),
    ], string='Acción', required=True, default='activity')
    summary = fields.Char(string='Resumen', default='Seguimiento del segmento')
    note = fields.Text(string='Nota de la actividad')
    deadline_days = fields.Integer(string='Vencimiento en días', default=3)
    activity_type_id = fields.Many2one('mail.activity.type', string='Tipo de actividad')
    tag_id = fields.Many2one('res.partner.category', string='Etiqueta')
    user_id = fields.Many2one('res.users', string='Vendedor')
    stage_id = fields.Many2one('crm.stage', string='Etapa')

    def _apply_to_partner(self, partner):
        self.ensure_one()
        if self.action_type == 'activity':
            activity_type = self.activity_type_id or self.env['mail.activity.type'].search(
                [('category', '=', 'default')], order='sequence, id', limit=1)
            if not activity_type:
                return False
            model_id = self.env['ir.model']._get_id('res.partner')
            existing = self.env['mail.activity'].search([
                ('res_model', '=', 'res.partner'), ('res_id', '=', partner.id),
                ('summary', '=', self.summary or 'Seguimiento del segmento'),
                ('user_id', '=', self.user_id.id or self.env.user.id),
                ('date_deadline', '>=', fields.Date.context_today(self)),
            ], limit=1)
            if not existing:
                self.env['mail.activity'].create({
                    'activity_type_id': activity_type.id,
                    'summary': self.summary or _('Seguimiento del segmento'),
                    'note': self.note or '',
                    'date_deadline': fields.Date.add(
                        fields.Date.context_today(self), days=self.deadline_days or 0),
                    'user_id': self.user_id.id or self.env.user.id,
                    'res_model_id': model_id,
                    'res_id': partner.id,
                })
            return True
        if self.action_type == 'tag' and self.tag_id:
            partner.write({'category_id': [(4, self.tag_id.id)]})
            return True
        leads = self.env['crm.lead'].search([
            ('partner_id', '=', partner.id), ('active', '=', True),
            ('stage_id.is_won', '=', False),
        ])
        if self.action_type == 'assign_user' and self.user_id:
            leads.write({'user_id': self.user_id.id})
            return bool(leads)
        if self.action_type == 'lead_stage' and self.stage_id:
            leads.write({'stage_id': self.stage_id.id})
            return bool(leads)
        return False

    def action_apply(self):
        for action in self:
            partners = action.segment_id.get_matching_partners()
            for partner in partners:
                today = fields.Date.context_today(action)
                already_applied = self.env['crm.rfm.segment.action.log'].search([
                    ('action_id', '=', action.id), ('partner_id', '=', partner.id),
                    ('applied_date', '=', today),
                ], limit=1)
                if already_applied:
                    continue
                if action._apply_to_partner(partner):
                    self.env['crm.rfm.segment.action.log'].create({
                        'action_id': action.id, 'segment_id': action.segment_id.id,
                        'partner_id': partner.id, 'applied_date': today,
                    })
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'title': _('Automatización ejecutada'),
            'message': _('Las acciones se aplicaron sobre los contactos del segmento.'),
            'type': 'success',
        }}


class RfmSegmentActionLog(models.Model):
    _name = 'crm.rfm.segment.action.log'
    _description = 'Histórico de automatización de segmento'
    _order = 'applied_date desc, id desc'

    action_id = fields.Many2one('crm.rfm.segment.action', required=True, ondelete='cascade')
    segment_id = fields.Many2one('crm.rfm.segment', required=True, ondelete='cascade')
    partner_id = fields.Many2one('res.partner', required=True, ondelete='cascade')
    applied_date = fields.Date(required=True, default=fields.Date.context_today)

    _action_partner_day_unique = models.Constraint(
        'unique(action_id, partner_id, applied_date)',
        'La automatización ya fue aplicada hoy a este contacto.')

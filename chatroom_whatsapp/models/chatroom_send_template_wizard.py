# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ChatroomSendTemplateWizard(models.TransientModel):
    _name = 'chatroom.send.template.wizard'
    _description = "Enviar plantilla de WhatsApp"

    channel_id = fields.Many2one('chatroom.channel', required=True)
    template_id = fields.Many2one(
        'chatroom.template', required=True, string="Plantilla",
        domain=[('status', '=', 'approved')])
    variable_count = fields.Integer(related='template_id.variable_count')
    variables_text = fields.Text(
        string="Variables",
        help="Un valor por línea, en el mismo orden que las variables "
             "{{1}}, {{2}}, ... de la plantilla.")
    preview = fields.Text(compute='_compute_preview')

    @api.depends('template_id', 'variables_text')
    def _compute_preview(self):
        for rec in self:
            body = rec.template_id.body or ''
            values = (rec.variables_text or '').splitlines()
            for index, value in enumerate(values, start=1):
                body = body.replace('{{%d}}' % index, value or '{{%d}}' % index)
            rec.preview = body

    def action_send(self):
        self.ensure_one()
        values = [v for v in (self.variables_text or '').splitlines()]
        self.channel_id.action_send_template(
            self.template_id.name, self.template_id.language, values)
        return {'type': 'ir.actions.act_window_close'}

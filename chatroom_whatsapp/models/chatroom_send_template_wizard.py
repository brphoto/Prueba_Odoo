# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


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
    mapping_preview = fields.Text(compute='_compute_mapping_preview')
    preview = fields.Text(compute='_compute_preview')

    @api.onchange('template_id')
    def _onchange_template_id(self):
        if self.template_id and self.channel_id:
            self.variables_text = '\n'.join(
                self.template_id.get_variable_values(self.channel_id))

    @api.depends('template_id', 'channel_id', 'variables_text')
    def _compute_mapping_preview(self):
        for rec in self:
            if not rec.template_id:
                rec.mapping_preview = ''
                continue
            values = (rec.variables_text or '').splitlines()
            mapping = {line.sequence: line for line in rec.template_id.variable_mapping_ids}
            rec.mapping_preview = '\n'.join(
                f'{{{{{number}}}}} · {mapping[number].label if number in mapping else _("Sin campo configurado")}: '
                f'{values[number - 1] if number <= len(values) and values[number - 1] else "(vacío)"}'
                for number in range(1, rec.template_id.variable_count + 1))

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
        if len(values) < self.template_id.variable_count or any(
                not values[index].strip()
                for index in range(self.template_id.variable_count)):
            raise UserError(_("Completa todas las variables antes de enviar la plantilla."))
        self.channel_id.action_send_template(
            self.template_id.name, self.template_id.language, values)
        return {'type': 'ir.actions.act_window_close'}

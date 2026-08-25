# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError


class ChatroomAiSandbox(models.Model):
    _name = 'chatroom.ai.sandbox'
    _description = 'Simulador seguro de IA'
    _order = 'write_date desc, id desc'

    name = fields.Char(string='Prueba', required=True, default=lambda self: _('Nueva simulacion'))
    channel_id = fields.Many2one('chatroom.channel', string='Contexto de conversacion')
    task_type = fields.Selection([
        ('reply', 'Respuesta'), ('summary', 'Resumen'),
        ('classification', 'Clasificacion'), ('next_action', 'Proxima accion'),
        ('agent', 'Agente'),
    ], string='Tipo de tarea', default='reply', required=True)
    prompt = fields.Text(string='Instruccion', required=True)
    output = fields.Text(string='Resultado', readonly=True)
    state = fields.Selection([
        ('draft', 'Borrador'), ('done', 'Completada'), ('error', 'Error'),
    ], default='draft', required=True)
    error_message = fields.Text(string='Detalle del error', readonly=True)
    model_used = fields.Char(string='Modelo utilizado', readonly=True)
    input_tokens = fields.Integer(string='Tokens de entrada', readonly=True)
    output_tokens = fields.Integer(string='Tokens de salida', readonly=True)

    def action_run(self):
        for record in self:
            if not record.channel_id:
                raise UserError(_('Selecciona una conversacion para aportar contexto.'))
            try:
                messages = record.channel_id._ai_build_conversation(extra_system=record.prompt)
                result = record.channel_id._ai_chat_completion(messages, task_type=record.task_type)
                record.write({'output': result, 'state': 'done', 'error_message': False})
                event = self.env['chatroom.ai.usage.event'].search([
                    ('channel_id', '=', record.channel_id.id),
                ], order='id desc', limit=1)
                if event:
                    record.write({
                        'model_used': event.model,
                        'input_tokens': event.input_tokens,
                        'output_tokens': event.output_tokens,
                    })
            except Exception as exc:
                record.write({'state': 'error', 'error_message': str(exc)})
                raise UserError(_('La simulacion fallo: %s') % exc) from exc
        return True

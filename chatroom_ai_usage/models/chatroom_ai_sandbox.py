# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
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
    scenario = fields.Selection([
        ('welcome', 'Bienvenida'), ('product', 'Consulta de producto'),
        ('quote', 'Preparar cotización'), ('payment', 'Cobranza'),
        ('complaint', 'Queja o escalamiento'),
    ], string='Escenario de prueba')
    expected_keywords = fields.Char(
        string='Debe incluir',
        help='Palabras separadas por coma. La prueba las valida sin distinguir mayúsculas.')
    prompt = fields.Text(string='Instruccion', required=True)
    output = fields.Text(string='Resultado', readonly=True)
    state = fields.Selection([
        ('draft', 'Borrador'), ('done', 'Completada'), ('error', 'Error'),
    ], default='draft', required=True)
    error_message = fields.Text(string='Detalle del error', readonly=True)
    model_used = fields.Char(string='Modelo utilizado', readonly=True)
    input_tokens = fields.Integer(string='Tokens de entrada', readonly=True)
    output_tokens = fields.Integer(string='Tokens de salida', readonly=True)
    evaluation_state = fields.Selection([
        ('pending', 'Pendiente'), ('passed', 'Aprobada'),
        ('warning', 'Revisar'), ('error', 'Error'),
    ], string='Evaluación', default='pending', readonly=True)
    evaluation_note = fields.Text(string='Resultado de evaluación', readonly=True)
    delivery_state = fields.Selection([
        ('not_run', 'Sin simular'), ('simulated', 'Entrega simulada'),
    ], string='WhatsApp', default='not_run', readonly=True)
    delivery_note = fields.Text(string='Detalle de entrega', readonly=True)

    _SCENARIOS = {
        'welcome': (_('Responde una bienvenida profesional y pregunta cómo podemos ayudar.'), 'ayudar'),
        'product': (_('Explica qué productos o servicios puede consultar el cliente y ofrece revisar el catálogo.'), 'producto,catálogo'),
        'quote': (_('Prepara una respuesta para solicitar alcance, usuarios, procesos y fecha objetivo antes de cotizar.'), 'alcance,usuarios'),
        'payment': (_('Prepara un mensaje de cobranza cordial; no envíes el mensaje ni inventes un enlace.'), 'pago,enlace'),
        'complaint': (_('Identifica la queja, responde con empatía y avisa que debe revisarla un asesor humano.'), 'asesor,disculpa'),
    }

    @api.onchange('scenario')
    def _onchange_scenario(self):
        if self.scenario in self._SCENARIOS:
            prompt, keywords = self._SCENARIOS[self.scenario]
            self.prompt = prompt
            self.expected_keywords = keywords

    def action_load_scenario(self):
        self._onchange_scenario()
        return {
            'type': 'ir.actions.act_window', 'name': _('Simulador seguro de IA'),
            'res_model': self._name, 'view_mode': 'form',
            'res_id': self.id, 'target': 'current',
        }

    def _evaluate_output(self, output):
        expected = [item.strip().lower() for item in (self.expected_keywords or '').split(',') if item.strip()]
        output_lower = (output or '').lower()
        missing = [item for item in expected if item not in output_lower]
        if not expected:
            return 'pending', _('No se definieron criterios automáticos; revisa el resultado manualmente.')
        if not missing:
            return 'passed', _('La respuesta contiene todos los criterios definidos.')
        return 'warning', _('Faltan criterios: %s. Revisa la respuesta antes de usarla.') % ', '.join(missing)

    def action_simulate_delivery(self):
        for record in self:
            if record.state != 'done' or not (record.output or '').strip():
                raise UserError(_('Ejecuta primero la prueba de IA para generar un mensaje de muestra.'))
            record.write({
                'delivery_state': 'simulated',
                'delivery_note': _('Entrega simulada correctamente. No se llamó a WhatsApp y no se creó ningún mensaje real.'),
            })
        return True

    def action_run(self):
        for record in self:
            if not record.channel_id:
                raise UserError(_('Selecciona una conversacion para aportar contexto.'))
            try:
                messages = record.channel_id._ai_build_conversation(extra_system=record.prompt)
                result = record.channel_id._ai_chat_completion(messages, task_type=record.task_type)
                evaluation_state, evaluation_note = record._evaluate_output(result)
                record.write({
                    'output': result, 'state': 'done', 'error_message': False,
                    'evaluation_state': evaluation_state,
                    'evaluation_note': evaluation_note,
                    'delivery_state': 'not_run', 'delivery_note': False,
                })
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
                record.write({'state': 'error', 'evaluation_state': 'error', 'error_message': str(exc)})
                raise UserError(_('La simulacion fallo: %s') % exc) from exc
        return True

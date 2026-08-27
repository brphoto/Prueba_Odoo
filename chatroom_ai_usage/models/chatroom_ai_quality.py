# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError


class ChatroomAiQualityTest(models.Model):
    _name = 'chatroom.ai.quality.test'
    _description = 'Prueba de calidad de respuestas IA'
    _order = 'active desc, name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Nombre', required=True)
    active = fields.Boolean(default=True)
    channel_id = fields.Many2one('chatroom.channel', string='Conversación de prueba', required=True)
    task_type = fields.Selection([
        ('reply', 'Respuesta'), ('summary', 'Resumen'),
        ('classification', 'Clasificación'), ('next_action', 'Próxima acción'),
        ('agent', 'Agente'),
    ], string='Tipo de prueba', default='reply', required=True)
    prompt = fields.Text(string='Instrucción adicional')
    expected_keywords = fields.Char(string='Palabras esperadas', help='Sepáralas por coma para medir cobertura básica.')
    last_run = fields.Datetime(string='Última ejecución', readonly=True)
    last_score = fields.Float(string='Último puntaje', readonly=True)
    last_state = fields.Selection([
        ('pending', 'Pendiente'), ('passed', 'Aprobada'), ('warning', 'Revisar'), ('error', 'Error'),
    ], string='Resultado', default='pending', readonly=True)
    last_output = fields.Text(string='Última respuesta', readonly=True)
    result_ids = fields.One2many('chatroom.ai.quality.result', 'test_id', string='Historial')

    def _score_output(self, output):
        self.ensure_one()
        keywords = [word.strip().lower() for word in (self.expected_keywords or '').split(',') if word.strip()]
        if not keywords:
            return 100.0
        text = (output or '').lower()
        return round(sum(1 for word in keywords if word in text) / len(keywords) * 100.0, 2)

    def action_run(self):
        for test in self:
            if not test.channel_id or not hasattr(test.channel_id, '_ai_chat_completion'):
                raise UserError(_('Selecciona una conversacion valida para la prueba.'))
            messages = test.channel_id._ai_build_conversation(extra_system=test.prompt or _('Responde de forma profesional y verificable.'))
            try:
                output = test.channel_id._ai_chat_completion(messages, task_type=test.task_type)
                score = test._score_output(output)
                state = 'passed' if score >= 80 else 'warning'
                test.write({'last_run': fields.Datetime.now(), 'last_score': score, 'last_state': state, 'last_output': output})
                self.env['chatroom.ai.quality.result'].create({
                    'test_id': test.id, 'run_date': fields.Datetime.now(),
                    'score': score, 'state': state, 'output': output,
                })
            except Exception as exc:
                test.write({'last_run': fields.Datetime.now(), 'last_state': 'error', 'last_output': str(exc)})
                self.env['chatroom.ai.quality.result'].create({
                    'test_id': test.id, 'run_date': fields.Datetime.now(),
                    'score': 0.0, 'state': 'error', 'output': str(exc),
                })
                raise UserError(_('La prueba de calidad fallo: %s') % exc) from exc
        return True

    def action_run_selected(self):
        """Ejecuta las pruebas seleccionadas sin detener toda la batería ante un fallo."""
        passed = warning = failed = 0
        for test in self:
            try:
                with self.env.cr.savepoint():
                    test.action_run()
                if test.last_state == 'passed':
                    passed += 1
                else:
                    warning += 1
            except UserError:
                failed += 1
        message = _('Aprobadas: %s. Para revisar: %s. Con error: %s.') % (passed, warning, failed)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Batería de pruebas IA'),
                'message': message,
                'type': 'success' if not failed and not warning else 'warning',
                'sticky': False,
            },
        }


class ChatroomAiQualityResult(models.Model):
    _name = 'chatroom.ai.quality.result'
    _description = 'Resultado de prueba IA'
    _order = 'run_date desc, id desc'

    test_id = fields.Many2one('chatroom.ai.quality.test', required=True, ondelete='cascade')
    run_date = fields.Datetime(string='Fecha', required=True, default=fields.Datetime.now)
    score = fields.Float(string='Puntaje')
    state = fields.Selection([
        ('passed', 'Aprobada'), ('warning', 'Revisar'), ('error', 'Error'),
    ], required=True)
    output = fields.Text(string='Respuesta')

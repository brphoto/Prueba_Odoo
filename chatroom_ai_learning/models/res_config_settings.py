# -*- coding: utf-8 -*-
from odoo import fields, models

PREFIX = 'chatroom_ai_learning.'


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    learning_graduated_autonomy = fields.Boolean(
        string='Autonomía por niveles', config_parameter=PREFIX + 'graduated_autonomy', default=True,
        help='Cada tipo de conversación responde sola solo cuando ganó ese nivel con datos.')
    learning_min_samples = fields.Integer(
        string='Evaluaciones mínimas', config_parameter=PREFIX + 'min_samples', default=30)
    learning_promote_rate = fields.Float(
        string='Acierto para responder sola (%)', config_parameter=PREFIX + 'promote_rate', default=90.0)
    learning_demote_rate = fields.Float(
        string='Acierto para volver a supervisado (%)', config_parameter=PREFIX + 'demote_rate', default=80.0)
    learning_window = fields.Integer(
        string='Evaluaciones recientes que cuentan', config_parameter=PREFIX + 'window', default=50)
    learning_shadow_enabled = fields.Boolean(
        string='Modo sombra', config_parameter=PREFIX + 'shadow_enabled', default=True,
        help='La IA redacta en silencio y se compara con lo que responde el equipo. No envía nada.')
    learning_shadow_rate = fields.Integer(
        string='Mensajes evaluados en sombra (%)', config_parameter=PREFIX + 'shadow_rate', default=50)
    learning_shadow_daily_limit = fields.Integer(
        string='Máximo diario en sombra', config_parameter=PREFIX + 'shadow_daily_limit', default=200)
    learning_handoff_enabled = fields.Boolean(
        string='Reglas de traspaso a una persona', config_parameter=PREFIX + 'handoff_enabled', default=True)
    learning_resume_after_hours = fields.Integer(
        string='Reactivar la IA tras (horas)', config_parameter=PREFIX + 'resume_after_hours', default=12,
        help='Si una persona tomó la conversación y ya respondió, la IA retoma tras estas horas sin '
             'actividad. 0 = nunca. Tras una respuesta no segura siempre hace falta una persona.')
    learning_memory_enabled = fields.Boolean(
        string='Memoria automática del cliente', config_parameter=PREFIX + 'memory_enabled', default=True)
    learning_memory_min_confidence = fields.Float(
        string='Confianza para guardar sin revisión', config_parameter=PREFIX + 'memory_min_confidence',
        default=0.8)
    learning_eval_min_pass_rate = fields.Float(
        string='Aprobación mínima de las pruebas (%)', config_parameter=PREFIX + 'eval_min_pass_rate',
        default=80.0, help='Por debajo, la autonomía se congela hasta que las pruebas vuelvan a pasar.')
    learning_autonomy_frozen = fields.Boolean(
        string='Autonomía congelada', config_parameter=PREFIX + 'autonomy_frozen', readonly=True)

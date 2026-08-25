# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class CrmStagnationConfig(models.Model):
    _name = 'crm.stagnation.config'
    _description = 'Reglas de oportunidades estancadas'
    _check_company_auto = True
    _order = 'company_id, id'

    name = fields.Char(string='Configuración', required=True, default='Reglas comerciales')
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', string='Empresa', required=True,
        default=lambda self: self.env.company, index=True)
    default_max_days = fields.Integer(string='Días máximos por defecto', default=30, required=True)
    warning_ratio = fields.Float(string='Umbral de precaución', default=0.70, required=True)
    critical_ratio = fields.Float(string='Umbral crítico', default=1.00, required=True)
    stagnant_ratio = fields.Float(string='Umbral estancada', default=1.50, required=True)
    dead_ratio = fields.Float(string='Umbral muerta', default=2.00, required=True)
    dead_no_activity_ratio = fields.Float(
        string='Ratio sin actividad para muerta', default=2.00, required=True,
        help='Una oportunidad se considera muerta cuando no tiene gestión humana durante este múltiplo del límite de su etapa.')
    high_activity_rate = fields.Float(string='Tasa alta de actividad', default=0.50, required=True)
    medium_activity_rate = fields.Float(string='Tasa media de actividad', default=0.20, required=True)
    low_activity_rate = fields.Float(string='Tasa baja de actividad', default=0.10, required=True)
    min_score_to_purge = fields.Float(string='Score máximo para recomendar depuración', default=30.0)
    capital_warning_factor = fields.Float(string='Capital atrapado: precaución', default=0.30)
    capital_critical_factor = fields.Float(string='Capital atrapado: crítico', default=0.60)
    capital_stagnant_factor = fields.Float(string='Capital atrapado: estancada', default=0.80)
    capital_dead_factor = fields.Float(string='Capital atrapado: muerta', default=0.95)
    notify_enabled = fields.Boolean(string='Enviar alertas', default=True)
    notification_level = fields.Selection([
        ('warning', 'Desde precaución'),
        ('critical', 'Desde crítico'),
        ('stagnant', 'Desde estancada'),
        ('dead', 'Solo muerta'),
    ], string='Nivel mínimo de alerta', default='critical', required=True)
    notification_repeat_days = fields.Integer(string='Repetir alerta cada (días)', default=2, required=True)
    escalation_enabled = fields.Boolean(string='Escalar al líder', default=True)
    escalation_after_days = fields.Integer(string='Escalar después de (días sobre límite)', default=5, required=True)
    require_reason = fields.Boolean(
        string='Exigir motivo en oportunidades estancadas', default=False,
        help='Si está activo, no permite guardar una oportunidad estancada sin motivo.')
    create_ai_tasks = fields.Boolean(
        string='Crear tareas supervisadas del agente IA', default=False,
        help='Solo funciona si está instalado el módulo Agente IA. Nunca envía mensajes ni ejecuta pagos automáticamente.')
    ai_task_level = fields.Selection([
        ('critical', 'Crítico o superior'),
        ('stagnant', 'Estancada o superior'),
        ('dead', 'Solo muerta'),
    ], string='Nivel mínimo para tarea IA', default='stagnant', required=True)
    last_run = fields.Datetime(string='Último cálculo', readonly=True)
    last_count = fields.Integer(string='Registros calculados', readonly=True)

    @api.constrains('default_max_days', 'warning_ratio', 'critical_ratio', 'stagnant_ratio', 'dead_ratio', 'dead_no_activity_ratio')
    def _check_thresholds(self):
        for config in self:
            if config.default_max_days < 1:
                raise ValidationError('Los días máximos deben ser mayores que cero.')
            ratios = [config.warning_ratio, config.critical_ratio, config.stagnant_ratio, config.dead_ratio]
            if any(value <= 0 for value in ratios) or ratios != sorted(ratios):
                raise ValidationError('Los umbrales deben ser positivos y estar ordenados.')
            if config.dead_no_activity_ratio <= 0:
                raise ValidationError('El ratio sin actividad debe ser mayor que cero.')

    @api.constrains('company_id', 'active')
    def _check_one_company_config(self):
        for config in self.filtered('active'):
            duplicate = self.search_count([
                ('id', '!=', config.id), ('company_id', '=', config.company_id.id), ('active', '=', True),
            ])
            if duplicate:
                raise ValidationError('Solo puede existir una configuración activa por empresa.')

    @api.model
    def get_for_company(self, company=False):
        company = company or self.env.company
        config = self.sudo().search([('company_id', '=', company.id), ('active', '=', True)], limit=1)
        if not config:
            config = self.sudo().create({
                'name': 'Reglas comerciales - %s' % company.display_name,
                'company_id': company.id,
            })
        return config

    @api.model
    def level_rank(self, level):
        return {'healthy': 0, 'warning': 1, 'critical': 2, 'stagnant': 3, 'dead': 4}.get(level or 'healthy', 0)

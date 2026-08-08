# -*- coding: utf-8 -*-
from datetime import date, datetime, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.safe_eval import safe_eval


class ChatroomKpiDefinition(models.Model):
    _name = 'chatroom.kpi.definition'
    _description = 'KPI configurable de Chatroom'
    _order = 'sequence, name'

    name = fields.Char(string='Nombre del KPI', required=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    model_name = fields.Selection([
        ('chatroom.channel', 'Conversaciones'),
        ('chatroom.message', 'Mensajes'),
        ('mail.activity', 'Actividades'),
    ], string='Modelo de análisis', required=True, default='chatroom.channel')
    aggregation = fields.Selection([
        ('count', 'Cantidad de registros'),
        ('sum', 'Suma'),
        ('avg', 'Promedio'),
    ], string='Cálculo', required=True, default='count')
    measure_field = fields.Selection([
        ('id', 'Identificador'),
        ('unread_count', 'Mensajes sin leer'),
        ('message_count', 'Mensajes de la conversación'),
        ('first_response_minutes', 'Minutos hasta primera respuesta'),
        ('pending_response_minutes', 'Minutos esperando respuesta'),
        ('csat_score', 'Calificación CSAT'),
        ('cart_total', 'Total del carrito'),
    ], string='Campo a medir', default='id')
    date_field = fields.Selection([
        ('none', 'Sin filtro de fecha'),
        ('create_date', 'Fecha de creación'),
        ('last_message_date', 'Último mensaje'),
        ('date', 'Fecha del mensaje'),
        ('date_deadline', 'Fecha límite de actividad'),
    ], string='Campo de fecha', required=True, default='create_date')
    domain_filter = fields.Text(
        string='Dominio adicional', default='[]',
        help="Dominio Odoo seguro, por ejemplo: [('state', '=', 'pending')]")
    format_type = fields.Selection([
        ('number', 'Número'), ('money', 'Moneda'), ('percent', 'Porcentaje'),
        ('minutes', 'Tiempo'),
    ], string='Formato mostrado', default='number', required=True)
    target_value = fields.Float(
        string='Objetivo',
        help='Valor de referencia para mostrar el semáforo gerencial.')
    goal_direction = fields.Selection([
        ('none', 'Sin objetivo'),
        ('higher', 'Mejor si es mayor o igual'),
        ('lower', 'Mejor si es menor o igual'),
    ], string='Semáforo', default='none', required=True)
    target_ids = fields.One2many('chatroom.kpi.target', 'kpi_id', string='Objetivos por alcance')

    _MODEL_FIELDS = {
        'chatroom.channel': {
            'id', 'unread_count', 'message_count', 'first_response_minutes',
            'pending_response_minutes', 'csat_score', 'cart_total',
            'create_date', 'last_message_date',
        },
        'chatroom.message': {'id', 'date', 'create_date'},
        'mail.activity': {'id', 'date_deadline', 'create_date'},
    }

    @api.onchange('model_name', 'aggregation')
    def _onchange_model_configuration(self):
        for record in self:
            valid_fields = self._MODEL_FIELDS.get(record.model_name, set())
            if record.measure_field not in valid_fields:
                record.measure_field = 'id'
            if record.date_field not in valid_fields and record.date_field != 'none':
                record.date_field = {
                    'chatroom.channel': 'create_date',
                    'chatroom.message': 'date',
                    'mail.activity': 'date_deadline',
                }.get(record.model_name, 'none')
            if record.aggregation == 'count':
                record.measure_field = 'id'

    @api.constrains('model_name', 'aggregation', 'measure_field', 'date_field',
                    'domain_filter', 'target_value', 'goal_direction')
    def _check_configuration(self):
        for record in self:
            valid_fields = self._MODEL_FIELDS[record.model_name]
            if record.measure_field not in valid_fields:
                raise ValidationError(_(
                    'El campo %s no pertenece al modelo %s.') % (
                        record.measure_field, record.model_name))
            if record.date_field != 'none' and record.date_field not in valid_fields:
                raise ValidationError(_(
                    'El campo de fecha %s no pertenece al modelo %s.') % (
                        record.date_field, record.model_name))
            try:
                domain = safe_eval(record.domain_filter or '[]', {
                    'uid': self.env.user.id,
                    'company_id': self.env.company.id,
                })
            except Exception as exc:
                raise ValidationError(_(
                    'El dominio adicional no es válido: %s') % exc)
            if not isinstance(domain, list):
                raise ValidationError(_('El dominio adicional debe ser una lista.'))
            if record.goal_direction != 'none' and record.target_value < 0:
                raise ValidationError(_('El objetivo no puede ser negativo.'))

    def _get_domain(self, period_days=30):
        self.ensure_one()
        try:
            domain = safe_eval(self.domain_filter or '[]', {
                'uid': self.env.user.id,
                'company_id': self.env.company.id,
            })
        except Exception as exc:
            raise ValidationError(_(
                'No se pudo interpretar el dominio del KPI: %s') % exc)
        if not isinstance(domain, list):
            raise ValidationError(_('El dominio del KPI debe ser una lista.'))
        try:
            period_days = int(period_days or 0)
        except (TypeError, ValueError):
            period_days = 30
        if period_days > 0 and self.date_field != 'none':
            date_from = fields.Datetime.subtract(fields.Datetime.now(), days=period_days)
            if self.date_field in ('create_date', 'last_message_date', 'date'):
                domain.extend([(self.date_field, '>=', date_from)])
            else:
                domain.extend([(
                    self.date_field, '>=', fields.Date.to_date(date_from))])
        return domain

    def _format_value(self, value):
        if self.format_type == 'money':
            return f'{self.env.company.currency_id.symbol} {value:,.2f}'.replace(
                ',', 'X').replace('.', ',').replace('X', '.')
        if self.format_type == 'percent':
            return f'{value:.1f}%'
        if self.format_type == 'minutes':
            minutes = max(0, round(value or 0))
            if minutes < 60:
                return f'{minutes} min'
            return f'{minutes // 60} h {minutes % 60:02d} min'
        return f'{value:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')

    def _get_effective_target(self):
        self.ensure_one()
        target = self.target_ids.filtered(
            lambda item: item.active and item.is_current_period() and item.scope_type == 'company' and
            item.company_id == self.env.company)[:1]
        target = target or self.target_ids.filtered(
            lambda item: item.active and item.is_current_period() and item.scope_type == 'global')[:1]
        return (target.target_value, target.goal_direction) if target else (
            self.target_value, self.goal_direction)

    def _compute_value(self, period_days=30):
        self.ensure_one()
        records = self.env[self.model_name].search(self._get_domain(period_days))
        if self.aggregation == 'count':
            value = float(len(records))
        else:
            values = [float(record[self.measure_field] or 0) for record in records]
            value = sum(values) if self.aggregation == 'sum' else (
                sum(values) / len(values) if values else 0.0)
        target_value, goal_direction = self._get_effective_target()
        status = 'neutral'
        if goal_direction == 'higher' and value >= target_value:
            status = 'success'
        elif goal_direction == 'lower' and value <= target_value:
            status = 'success'
        elif goal_direction != 'none':
            status = 'danger'
        return {
            'id': self.id,
            'name': self.name,
            'value': value,
            'display_value': self._format_value(value),
            'model': self.model_name,
            'domain': [
                tuple(str(value) if isinstance(value, (date, datetime)) else value
                      for value in term)
                if isinstance(term, (list, tuple)) else term
                for term in self._get_domain(period_days)
            ],
            'target_value': target_value,
            'target_display': self._format_value(target_value),
            'goal_direction': goal_direction,
            'status': status,
        }

    @api.model
    def get_dashboard_values(self, period_days=30):
        return [record._compute_value(period_days) for record in self.search([
            ('active', '=', True)], order='sequence, name')]

    def action_test_kpi(self):
        self.ensure_one()
        result = self._compute_value(30)
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'title': _('KPI probado'),
            'message': f"{self.name}: {result['display_value']}",
            'type': 'success',
        }}

    def action_view_snapshots(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Histórico: %s') % self.name,
            'res_model': 'chatroom.kpi.snapshot',
            'view_mode': 'graph,list',
            'domain': [('kpi_id', '=', self.id)],
            'context': {'search_default_group_date': 1},
        }

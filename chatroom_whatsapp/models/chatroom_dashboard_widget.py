# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ChatroomDashboardWidget(models.Model):
    _name = 'chatroom.dashboard.widget'
    _description = 'Widget configurable del dashboard de Chatroom'
    _order = 'sequence, name'

    name = fields.Char(string='Nombre del widget', required=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    widget_type = fields.Selection([
        ('card', 'Tarjeta numérica'),
        ('bar', 'Gráfico de barras'),
        ('line', 'Gráfico de líneas'),
        ('pie', 'Gráfico circular'),
    ], string='Tipo de widget', required=True, default='card')
    source_type = fields.Selection([
        ('kpi', 'KPI configurable'),
        ('stage', 'Conversaciones por etapa'),
        ('agent', 'Conversaciones por agente'),
        ('response', 'Respuesta promedio por agente'),
    ], string='Fuente de datos', required=True, default='kpi')
    kpi_id = fields.Many2one(
        'chatroom.kpi.definition', string='KPI',
        domain=[('active', '=', True)])
    limit = fields.Integer(
        string='Cantidad máxima', default=8,
        help='Cantidad de categorías o agentes mostrados en el gráfico.')
    color = fields.Char(string='Color', default='#714B67')
    note = fields.Char(string='Descripción corta')

    @api.constrains('source_type', 'kpi_id', 'limit')
    def _check_configuration(self):
        for record in self:
            if record.source_type == 'kpi' and not record.kpi_id:
                raise ValidationError(_('Selecciona un KPI para este widget.'))
            if record.limit < 1 or record.limit > 50:
                raise ValidationError(_('La cantidad máxima debe estar entre 1 y 50.'))

    @api.onchange('source_type')
    def _onchange_source_type(self):
        for record in self:
            if record.source_type != 'kpi':
                record.kpi_id = False
            if record.source_type == 'stage':
                record.widget_type = 'bar'
            elif record.source_type in ('agent', 'response'):
                record.widget_type = 'bar'

    def _series_for_source(self, period_days):
        self.ensure_one()
        channels = self.env['chatroom.channel']
        if self.source_type == 'kpi':
            result = self.kpi_id._compute_value(period_days)
            points = []
            snapshot_period = period_days or 30
            snapshots = self.env['chatroom.kpi.snapshot'].search([
                ('kpi_id', '=', self.kpi_id.id),
                ('period_days', '=', snapshot_period),
            ], order='snapshot_date asc', limit=50)
            for snapshot in snapshots:
                points.append({
                    'label': fields.Date.to_string(snapshot.snapshot_date),
                    'value': snapshot.value,
                    'display_value': snapshot.display_value,
                })
            if not points:
                points = [{'label': self.kpi_id.name, 'value': result['value'],
                           'display_value': result['display_value']}]
            return {
                'label': self.kpi_id.name,
                'value': result['value'],
                'display_value': result['display_value'],
                'target_display': result['target_display'],
                'status': result['status'],
                'points': points[-self.limit:],
            }

        data = channels.get_dashboard_data(period_days, agent_limit=self.limit,
                                           include_widgets=False)
        if self.source_type == 'stage':
            rows = data.get('stage_breakdown', [])
            return {'points': [
                {'label': row['name'], 'value': row['count'],
                 'display_value': str(row['count'])}
                for row in rows[:self.limit]
            ]}
        if self.source_type == 'response':
            rows = data.get('response_by_agent', [])
            return {'points': [
                {'label': row['name'], 'value': row['minutes'],
                 'display_value': f"{row['minutes']} min"}
                for row in rows[:self.limit]
            ]}
        rows = data.get('by_agent', [])
        return {'points': [
            {'label': row['name'], 'value': row['count'],
             'display_value': str(row['count'])}
            for row in rows[:self.limit]
        ]}

    @api.model
    def get_dashboard_values(self, period_days=30, widget_ids=None):
        widgets = self.browse(widget_ids).exists() if widget_ids else self.search(
            [('active', '=', True)], order='sequence, name')
        return [{
            'id': widget.id,
            'name': widget.name,
            'note': widget.note or '',
            'type': widget.widget_type,
            'source_type': widget.source_type,
            'color': widget.color or '#714B67',
            **widget._series_for_source(period_days),
        } for widget in widgets.filtered('active')]

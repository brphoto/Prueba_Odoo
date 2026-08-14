# -*- coding: utf-8 -*-
from datetime import date, datetime, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.safe_eval import safe_eval


class CrmKpiDefinition(models.Model):
    _name = 'crm.kpi.definition'
    _description = 'KPI configurable de inteligencia comercial'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, name'

    name = fields.Char(string='Nombre del KPI', required=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    model_name = fields.Selection([
        ('res.partner', 'Contactos'),
        ('sale.order', 'Presupuestos / pedidos'),
        ('account.move', 'Facturas'),
        ('crm.lead', 'Oportunidades'),
        ('mail.activity', 'Actividades'),
    ], string='Modelo de análisis', required=True, default='sale.order')
    aggregation = fields.Selection([
        ('count', 'Cantidad de registros'),
        ('sum', 'Suma'),
        ('avg', 'Promedio'),
    ], string='Cálculo', required=True, default='count')
    measure_field = fields.Selection([
        ('amount_total', 'Total'),
        ('amount_residual', 'Saldo pendiente'),
        ('expected_revenue', 'Ingreso esperado'),
        ('probability', 'Probabilidad'),
        ('id', 'Identificador'),
    ], string='Campo a medir', default='amount_total')
    date_field = fields.Selection([
        ('none', 'Sin filtro de fecha'),
        ('invoice_date', 'Fecha de factura'),
        ('date_order', 'Fecha del pedido'),
        ('create_date', 'Fecha de creación'),
        ('date_last_stage_update', 'Última actualización de etapa'),
        ('date_deadline', 'Fecha límite'),
    ], string='Campo de fecha', default='date_order', required=True)
    domain_filter = fields.Text(
        string='Dominio adicional', default='[]',
        help="Dominio Odoo seguro, por ejemplo: [('state', '=', 'sale')]")
    formula = fields.Char(
        string='Fórmula opcional',
        help="Expresión numérica sobre value y record_count. Ejemplo: value * 100 / 500")
    compare_previous = fields.Boolean(string='Comparar con período anterior', default=True)
    format_type = fields.Selection([
        ('number', 'Número'), ('money', 'Moneda'), ('percent', 'Porcentaje'),
    ], string='Formato mostrado', default='number', required=True)
    target_value = fields.Float(string='Objetivo')
    goal_direction = fields.Selection([
        ('none', 'Sin objetivo'),
        ('higher', 'Mejor si es mayor o igual'),
        ('lower', 'Mejor si es menor o igual'),
    ], string='Semáforo', default='none', required=True)
    target_ids = fields.One2many('crm.kpi.target', 'kpi_id', string='Objetivos por alcance')

    _MODEL_FIELDS = {
        'res.partner': {'id', 'create_date'},
        'sale.order': {'id', 'amount_total', 'date_order'},
        'account.move': {'id', 'amount_total', 'amount_residual', 'invoice_date'},
        'crm.lead': {'id', 'expected_revenue', 'probability', 'create_date', 'date_last_stage_update'},
        'mail.activity': {'id', 'date_deadline'},
    }

    # El filtro también usa el catálogo configurable de categorías RFM.
    rfm_category = fields.Selection(
        selection='_selection_rfm_category_filter', string='Categoría RFM', default='all')

    @api.model
    def _selection_rfm_category_filter(self):
        options = [('all', 'Todas')]
        try:
            options += self.env['res.partner']._selection_rfm_category()
        except Exception:
            options += [
                ('a', 'A - Alto valor'), ('b', 'B - Valor medio'),
                ('c', 'C - Bajo valor'), ('none', 'Sin historial'),
            ]
        return options

    @api.onchange('model_name', 'aggregation')
    def _onchange_model_configuration(self):
        date_defaults = {
            'res.partner': 'create_date', 'sale.order': 'date_order',
            'account.move': 'invoice_date', 'crm.lead': 'create_date',
            'mail.activity': 'date_deadline',
        }
        for record in self:
            valid_fields = self._MODEL_FIELDS.get(record.model_name, set())
            if record.measure_field not in valid_fields:
                record.measure_field = 'id' if record.aggregation == 'count' else next(
                    (field for field in ('amount_total', 'expected_revenue', 'probability')
                     if field in valid_fields), 'id')
            if record.date_field not in valid_fields and record.date_field != 'none':
                record.date_field = date_defaults.get(record.model_name, 'none')

    @api.constrains('model_name', 'aggregation', 'measure_field', 'date_field', 'domain_filter')
    def _check_configuration(self):
        for record in self:
            if record.measure_field and record.measure_field not in self._MODEL_FIELDS[record.model_name]:
                raise ValidationError(_("El campo %s no pertenece al modelo %s.") % (
                    record.measure_field, record.model_name))
            if record.date_field != 'none' and record.date_field not in self._MODEL_FIELDS[record.model_name]:
                raise ValidationError(_("El campo de fecha %s no pertenece al modelo %s.") % (
                    record.date_field, record.model_name))
            try:
                domain = safe_eval(record.domain_filter or '[]', {'uid': self.env.user.id})
            except Exception as exc:
                raise ValidationError(_("El dominio adicional no es válido: %s") % exc)
            if not isinstance(domain, list):
                raise ValidationError(_("El dominio adicional debe ser una lista."))

    @api.constrains('formula')
    def _check_formula(self):
        for record in self.filtered('formula'):
            try:
                result = safe_eval(record.formula, {
                    'value': 1.0, 'record_count': 1, 'period': '90', 'category': 'all',
                })
                float(result)
            except Exception as exc:
                raise ValidationError(_("La fórmula debe devolver un número: %s") % exc)

    def _get_domain(self, period='90', category='all'):
        self.ensure_one()
        try:
            domain = safe_eval(self.domain_filter or '[]', {'uid': self.env.user.id})
        except Exception as exc:
            raise ValidationError(_("No se pudo interpretar el dominio del KPI: %s") % exc)
        if not isinstance(domain, list):
            raise ValidationError(_("El dominio del KPI debe ser una lista."))
        if self.model_name == 'res.partner' and category and category != 'all':
            domain.append(('rfm_category', '=', category))
        if period in ('30', '90', '365') and self.date_field != 'none':
            today = fields.Date.context_today(self)
            date_from = today - timedelta(days=int(period))
            if self.date_field in ('create_date', 'date_order', 'date_last_stage_update'):
                domain.extend([
                    (self.date_field, '>=', fields.Datetime.to_datetime(date_from)),
                    (self.date_field, '<', fields.Datetime.to_datetime(today + timedelta(days=1))),
                ])
            else:
                domain.append((self.date_field, '>=', date_from))
        return domain

    def _format_kpi_value(self, value):
        """Formatea un número según format_type: evita repetir el mismo
        reemplazo de separadores de miles/decimales varias veces por
        cada llamada a _compute_value (antes se repetía 4 veces, dos de
        ellas sobre un valor que ni siquiera se terminaba usando)."""
        self.ensure_one()
        if self.format_type == 'money':
            return f'{self.env.company.currency_id.symbol} {value:,.2f}'.replace(
                ',', 'X').replace('.', ',').replace('X', '.')
        if self.format_type == 'percent':
            return f'{value:.1f}%'
        return f'{value:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')

    def _compute_value(self, period='90', category='all'):
        self.ensure_one()
        domain = self._get_domain(period, category)
        records = self.env[self.model_name].search(domain)
        if self.aggregation == 'count':
            value = len(records)
        else:
            values = [float(record[self.measure_field] or 0) for record in records]
            value = sum(values) if self.aggregation == 'sum' else (sum(values) / len(values) if values else 0)
        if self.formula:
            try:
                value = float(safe_eval(self.formula, {
                    'value': value, 'record_count': len(records),
                    'period': period, 'category': category,
                }))
            except Exception as exc:
                raise ValidationError(_("No se pudo calcular la fórmula del KPI %s: %s") % (self.name, exc))
        display = self._format_kpi_value(value)
        target = self.target_ids.filtered(
            lambda item: item.active and item.is_current_period() and item.scope_type == 'company' and
            item.company_id == self.env.company)[:1]
        target = target or self.target_ids.filtered(
            lambda item: item.active and item.is_current_period() and item.scope_type == 'global')[:1]
        target_value = target.target_value if target else self.target_value
        goal_direction = target.goal_direction if target else self.goal_direction
        progress = False
        if goal_direction == 'higher' and target_value:
            progress = round(value / target_value * 100, 1)
        elif goal_direction == 'lower' and target_value:
            progress = round(target_value / value * 100, 1) if value else 100.0
        return {
            'id': self.id, 'name': self.name, 'value': value,
            'display_value': display, 'model': self.model_name,
            'domain': [
                tuple(str(value) if isinstance(value, (date, datetime)) else value
                      for value in term)
                if isinstance(term, (list, tuple)) else term
                for term in domain
            ],
            'target_value': target_value,
            'target_display': (
                f'{self.env.company.currency_id.symbol} {target_value:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
                if self.format_type == 'money' else
                f'{target_value:.1f}%' if self.format_type == 'percent' else
                f'{target_value:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
            ),
            'goal_direction': goal_direction,
            'progress': progress,
            'status': (
                'success' if (
                    goal_direction == 'higher' and value >= target_value) or
                    (goal_direction == 'lower' and value <= target_value)
                else 'danger' if goal_direction != 'none' else 'neutral'
            ),
        }

    @api.model
    def get_dashboard_values(self, period='90', category='all'):
        return [record._compute_value(period, category) for record in self.search([('active', '=', True)])]

    def action_test_kpi(self):
        self.ensure_one()
        value = self._compute_value('90', 'all')['display_value']
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'title': _('KPI probado'), 'message': f'{self.name}: {value}', 'type': 'success'}}

    def action_view_snapshots(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Histórico: %s') % self.name,
            'res_model': 'crm.kpi.snapshot',
            'view_mode': 'graph,list',
            'domain': [('kpi_id', '=', self.id)],
        }

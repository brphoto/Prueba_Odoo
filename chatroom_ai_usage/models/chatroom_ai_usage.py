# -*- coding: utf-8 -*-
import json
from datetime import datetime, timedelta

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ChatroomAiUsageEvent(models.Model):
    _name = 'chatroom.ai.usage.event'
    _description = 'Consumo local de IA'
    _order = 'request_date desc, id desc'

    request_date = fields.Datetime(string='Fecha', required=True, default=fields.Datetime.now, index=True)
    company_id = fields.Many2one(
        'res.company', string='Empresa', required=True, index=True,
        default=lambda self: self.env.company,
    )
    model = fields.Char(string='Modelo', index=True)
    task_type = fields.Selection([
        ('general', 'General'), ('reply', 'Respuesta'), ('summary', 'Resumen'),
        ('classification', 'Clasificación'), ('next_action', 'Próxima acción'),
        ('agent', 'Agente'),
    ], string='Tipo de tarea', default='general', index=True)
    channel_id = fields.Many2one('chatroom.channel', string='Conversacion', ondelete='set null', index=True)
    input_tokens = fields.Integer(string='Tokens de entrada')
    output_tokens = fields.Integer(string='Tokens de salida')
    total_tokens = fields.Integer(string='Tokens totales')
    success = fields.Boolean(string='Correcta', default=True)

    @api.model_create_multi
    def create(self, vals_list):
        """Asigna la empresa de la conversación cuando el evento la tiene."""
        for values in vals_list:
            if values.get('channel_id') and not values.get('company_id'):
                channel = self.env['chatroom.channel'].sudo().browse(
                    values['channel_id']).exists()
                if channel and channel.company_id:
                    values['company_id'] = channel.company_id.id
        return super().create(vals_list)


class ChatroomAiUsageSnapshot(models.Model):
    _name = 'chatroom.ai.usage.snapshot'
    _description = 'Resumen de consumo de IA'
    _order = 'fetched_at desc, id desc'

    name = fields.Char(string='Resumen', required=True)
    company_id = fields.Many2one(
        'res.company', string='Empresa', required=True, index=True,
        default=lambda self: self.env.company,
    )
    fetched_at = fields.Datetime(string='Actualizado', required=True, default=fields.Datetime.now, readonly=True)
    period_start = fields.Datetime(string='Desde', required=True, readonly=True)
    period_end = fields.Datetime(string='Hasta', required=True, readonly=True)
    request_count = fields.Integer(string='Solicitudes')
    input_tokens = fields.Integer(string='Tokens de entrada')
    output_tokens = fields.Integer(string='Tokens de salida')
    total_tokens = fields.Integer(string='Tokens totales')
    cost = fields.Float(string='Costo oficial', digits=(16, 6))
    currency = fields.Char(string='Moneda', default='usd')
    budget_limit = fields.Float(string='Presupuesto de referencia', digits=(16, 2))
    budget_remaining = fields.Float(string='Saldo estimado', digits=(16, 2))
    budget_percent = fields.Float(string='Porcentaje utilizado', digits=(16, 2))
    budget_state = fields.Selection([
        ('no_limit', 'Sin presupuesto'), ('ok', 'Normal'),
        ('warning', 'Alerta'), ('exceeded', 'Excedido'),
    ], string='Estado del presupuesto', default='no_limit')
    local_request_count = fields.Integer(string='Solicitudes locales')
    local_total_tokens = fields.Integer(string='Tokens locales')
    model_breakdown = fields.Text(string='Detalle por modelo', readonly=True)
    state = fields.Selection([
        ('ok', 'Actualizado'), ('partial', 'Solo consumo local'), ('error', 'Error'),
    ], default='ok', required=True)
    error_message = fields.Text(string='Detalle')

    def _notify_budget_alert(self):
        """Crea una actividad visible para administradores sin enviar correos secretos."""
        todo = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        system_group = self.env.ref('base.group_system', raise_if_not_found=False)
        if not todo or not system_group or self.budget_state not in ('warning', 'exceeded'):
            return
        admins = system_group.all_user_ids.sudo()
        activity = self.env['mail.activity'].sudo()
        for user in admins:
            duplicate = activity.search_count([
                ('res_model', '=', self._name), ('res_id', '=', self.id),
                ('user_id', '=', user.id), ('activity_type_id', '=', todo.id),
            ])
            if not duplicate:
                activity.create({
                    'activity_type_id': todo.id, 'res_model_id': self.env['ir.model']._get(self._name).id,
                    'res_id': self.id, 'user_id': user.id,
                    'summary': _('Revisar presupuesto de IA'),
                    'note': _('El consumo de IA esta en estado %s: %.2f%% del presupuesto de referencia.') % (self.budget_state, self.budget_percent),
                })

    @api.model
    def _api_base(self):
        return self.env['chatroom.ai.provider.model']._api_base()

    @api.model
    def _days(self):
        raw = self.env['ir.config_parameter'].sudo().get_param('chatroom_whatsapp.ai_usage_days', '31')
        try:
            return min(max(int(raw), 1), 31)
        except (TypeError, ValueError):
            return 31

    @api.model
    def _local_totals(self, start, end):
        events = self.env['chatroom.ai.usage.event'].sudo().search([
            ('request_date', '>=', start), ('request_date', '<', end),
            ('company_id', '=', self.env.company.id),
        ])
        return len(events), sum(events.mapped('total_tokens'))

    @api.model
    def _budget_values(self, cost):
        raw = self.env['ir.config_parameter'].sudo().get_param('chatroom_whatsapp.ai_monthly_budget', '0')
        try:
            limit = max(float(raw or 0.0), 0.0)
        except (TypeError, ValueError):
            limit = 0.0
        if not limit:
            return {'budget_limit': 0.0, 'budget_remaining': 0.0, 'budget_percent': 0.0, 'budget_state': 'no_limit'}
        percent = max(float(cost or 0.0), 0.0) / limit * 100.0
        return {
            'budget_limit': limit,
            'budget_remaining': max(limit - float(cost or 0.0), 0.0),
            'budget_percent': percent,
            'budget_state': 'exceeded' if percent >= 100 else 'warning' if percent >= 80 else 'ok',
        }

    @api.model
    def _fetch(self, path, key, start_ts, end_ts):
        params = {
            'start_time': start_ts,
            'end_time': end_ts,
            'bucket_width': '1d',
            'limit': 31,
            'group_by': 'model',
        }
        response = requests.get(
            '%s/%s' % (self._api_base(), path),
            headers={'Authorization': 'Bearer %s' % key},
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    @api.model
    def action_refresh_local(self):
        """Genera un resumen inmediato desde las solicitudes registradas en Odoo."""
        now = fields.Datetime.now()
        start = now - timedelta(days=self._days())
        local_count, local_tokens = self._local_totals(start, now)
        snapshot = self.sudo().create({
            'name': _('IA - resumen local de los últimos %s días') % self._days(),
            'company_id': self.env.company.id,
            'fetched_at': now,
            'period_start': start,
            'period_end': now,
            'request_count': local_count,
            'total_tokens': local_tokens,
            'local_request_count': local_count,
            'local_total_tokens': local_tokens,
            'currency': 'usd',
            'model_breakdown': '{}',
            'state': 'partial',
            'error_message': _('Resumen local basado en las solicitudes registradas. Para costos oficiales configura la Admin API Key.'),
        })
        snapshot._notify_budget_alert()
        return snapshot

    @api.model
    def action_refresh_local_ui(self):
        snapshot = self.action_refresh_local()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Consumo local actualizado'),
                'message': _('Se registraron %s solicitudes y %s tokens.') % (
                    snapshot.local_request_count, snapshot.local_total_tokens),
                'type': 'success',
                'sticky': False,
            },
        }

    @api.model
    def action_refresh(self):
        icp = self.env['ir.config_parameter'].sudo()
        admin_key = icp.get_param('chatroom_whatsapp.ai_admin_api_key')
        now = fields.Datetime.now()
        start = now - timedelta(days=self._days())
        local_count, local_tokens = self._local_totals(start, now)
        values = {
            'name': _('IA - últimos %s días') % self._days(),
            'company_id': self.env.company.id,
            'fetched_at': now,
            'period_start': start,
            'period_end': now,
            'local_request_count': local_count,
            'local_total_tokens': local_tokens,
            'currency': 'usd',
            'model_breakdown': '{}',
        }
        values.update(self._budget_values(0.0))
        if not admin_key:
            values.update({
                'state': 'partial',
                'request_count': local_count,
                'total_tokens': local_tokens,
                'error_message': _('Configura una Admin API Key para consultar costos oficiales de la organización.'),
            })
            snapshot = self.sudo().create(values)
            snapshot._notify_budget_alert()
            return {
                'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'title': _('Consumo local actualizado'), 'message': _('Registra %s solicitudes. Falta la Admin API Key para costos oficiales.') % local_count, 'type': 'warning', 'sticky': False},
            }

        start_ts = int(datetime.utcnow().timestamp()) - (self._days() * 86400)
        end_ts = int(datetime.utcnow().timestamp()) + 1
        try:
            usage = self._fetch('organization/usage/completions', admin_key, start_ts, end_ts)
            costs = self._fetch('organization/costs', admin_key, start_ts, end_ts)
            request_count = input_tokens = output_tokens = 0
            by_model = {}
            for bucket in usage.get('data', []):
                for result in bucket.get('results', []):
                    request_count += int(result.get('num_model_requests') or 0)
                    input_tokens += int(result.get('input_tokens') or 0)
                    output_tokens += int(result.get('output_tokens') or 0)
                    model = result.get('model') or _('Sin modelo')
                    by_model[model] = by_model.get(model, 0) + int(result.get('num_model_requests') or 0)
            total_tokens = input_tokens + output_tokens
            cost = 0.0
            currency = 'usd'
            for bucket in costs.get('data', []):
                for result in bucket.get('results', []):
                    amount = result.get('amount') or {}
                    cost += float(amount.get('value') or 0.0)
                    currency = amount.get('currency') or currency
            values.update({
                'request_count': request_count,
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'total_tokens': total_tokens,
                'cost': cost,
                'currency': currency,
                'model_breakdown': json.dumps(by_model, ensure_ascii=False, indent=2),
                'state': 'ok',
                'error_message': False,
            })
            values.update(self._budget_values(cost))
            snapshot = self.sudo().create(values)
            snapshot._notify_budget_alert()
            return {
                'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'title': _('Consumo de IA actualizado'), 'message': _('Solicitudes: %s | Costo: %.6f %s') % (request_count, cost, currency.upper()), 'type': 'success', 'sticky': False},
            }
        except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
            values.update({'state': 'error', 'error_message': str(exc)})
            self.sudo().create(values)
            raise UserError(_('No se pudo consultar el consumo de OpenAI Platform: %s') % exc) from exc

    @api.model
    def _cron_refresh_usage(self):
        enabled = self.env['ir.config_parameter'].sudo().get_param(
            'chatroom_whatsapp.ai_usage_auto_refresh', 'False') == 'True'
        if not enabled:
            return 0
        try:
            self.action_refresh()
            return 1
        except UserError:
            self.env.cr.rollback()
            return 0

    def action_open_platform_usage(self):
        return {
            'type': 'ir.actions.act_url',
            'url': 'https://platform.openai.com/usage',
            'target': 'new',
        }

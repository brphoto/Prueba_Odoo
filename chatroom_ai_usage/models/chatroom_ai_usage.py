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
    model = fields.Char(string='Modelo', index=True)
    channel_id = fields.Many2one('chatroom.channel', string='Conversacion', ondelete='set null', index=True)
    input_tokens = fields.Integer(string='Tokens de entrada')
    output_tokens = fields.Integer(string='Tokens de salida')
    total_tokens = fields.Integer(string='Tokens totales')
    success = fields.Boolean(string='Correcta', default=True)


class ChatroomAiUsageSnapshot(models.Model):
    _name = 'chatroom.ai.usage.snapshot'
    _description = 'Resumen de consumo de IA'
    _order = 'fetched_at desc, id desc'

    name = fields.Char(string='Resumen', required=True)
    fetched_at = fields.Datetime(string='Actualizado', required=True, default=fields.Datetime.now, readonly=True)
    period_start = fields.Datetime(string='Desde', required=True, readonly=True)
    period_end = fields.Datetime(string='Hasta', required=True, readonly=True)
    request_count = fields.Integer(string='Solicitudes')
    input_tokens = fields.Integer(string='Tokens de entrada')
    output_tokens = fields.Integer(string='Tokens de salida')
    total_tokens = fields.Integer(string='Tokens totales')
    cost = fields.Float(string='Costo oficial', digits=(16, 6))
    currency = fields.Char(string='Moneda', default='usd')
    local_request_count = fields.Integer(string='Solicitudes locales')
    local_total_tokens = fields.Integer(string='Tokens locales')
    model_breakdown = fields.Text(string='Detalle por modelo', readonly=True)
    state = fields.Selection([
        ('ok', 'Actualizado'), ('partial', 'Solo consumo local'), ('error', 'Error'),
    ], default='ok', required=True)
    error_message = fields.Text(string='Detalle')

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
        ])
        return len(events), sum(events.mapped('total_tokens'))

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
    def action_refresh(self):
        icp = self.env['ir.config_parameter'].sudo()
        admin_key = icp.get_param('chatroom_whatsapp.ai_admin_api_key')
        now = fields.Datetime.now()
        start = now - timedelta(days=self._days())
        local_count, local_tokens = self._local_totals(start, now)
        values = {
            'name': _('IA - ultimos %s dias') % self._days(),
            'fetched_at': now,
            'period_start': start,
            'period_end': now,
            'local_request_count': local_count,
            'local_total_tokens': local_tokens,
            'currency': 'usd',
            'model_breakdown': '{}',
        }
        if not admin_key:
            values.update({
                'state': 'partial',
                'request_count': local_count,
                'total_tokens': local_tokens,
                'error_message': _('Configura una Admin API Key para consultar costos oficiales de la organizacion.'),
            })
            self.sudo().create(values)
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
            self.sudo().create(values)
            return {
                'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'title': _('Consumo de IA actualizado'), 'message': _('Solicitudes: %s | Costo: %.6f %s') % (request_count, cost, currency.upper()), 'type': 'success', 'sticky': False},
            }
        except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
            values.update({'state': 'error', 'error_message': str(exc)})
            self.sudo().create(values)
            raise UserError(_('No se pudo consultar el consumo de OpenAI Platform: %s') % exc) from exc

# -*- coding: utf-8 -*-
import json
from datetime import datetime, timedelta

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ChatroomAiFunding(models.Model):
    _name = 'chatroom.ai.funding'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Fondos y conciliacion de IA'
    _order = 'movement_date desc, id desc'

    name = fields.Char(string='Descripción', required=True, default=lambda self: _('Recarga de créditos'))
    company_id = fields.Many2one(
        'res.company', string='Empresa', required=True, index=True,
        default=lambda self: self.env.company,
    )
    movement_date = fields.Date(string='Fecha', required=True, default=fields.Date.context_today, index=True)
    movement_type = fields.Selection([
        ('credit', 'Fondo / recarga'),
        ('debit', 'Ajuste / retiro'),
    ], string='Tipo de movimiento', required=True, default='credit')
    amount = fields.Float(string='Importe', required=True, digits=(16, 6))
    currency = fields.Char(string='Moneda', required=True, default='usd')
    signed_amount = fields.Float(string='Importe neto', compute='_compute_signed_amount', store=True, digits=(16, 6))
    reference = fields.Char(string='Referencia')
    note = fields.Text(string='Nota')

    @api.depends('movement_type', 'amount')
    def _compute_signed_amount(self):
        for record in self:
            record.signed_amount = record.amount if record.movement_type == 'credit' else -record.amount

    @api.constrains('amount')
    def _check_amount(self):
        for record in self:
            if record.amount <= 0:
                raise UserError(_('El importe del movimiento debe ser mayor que cero.'))

    def action_open_platform_billing(self):
        return {
            'type': 'ir.actions.act_url',
            'url': 'https://platform.openai.com/settings/organization/billing/overview',
            'target': 'new',
        }


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
    channel_id = fields.Many2one('chatroom.channel', string='Conversación', ondelete='set null', index=True)
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
    funding_total = fields.Float(string='Fondos registrados', digits=(16, 6))
    funding_debits = fields.Float(string='Ajustes / retiros', digits=(16, 6))
    funding_net = fields.Float(string='Fondos netos', digits=(16, 6))
    estimated_balance = fields.Float(string='Saldo de control estimado', digits=(16, 6))
    funding_currency = fields.Char(string='Moneda de fondos', default='usd')
    funding_entry_count = fields.Integer(string='Movimientos de fondos')
    financial_state = fields.Selection([
        ('unconfigured', 'Sin fondos registrados'),
        ('available', 'Saldo de control disponible'),
        ('exhausted', 'Consumo superior al fondo'),
        ('mismatch', 'Revisar moneda'),
    ], string='Estado financiero', default='unconfigured')
    billing_reconciliation_note = fields.Text(string='Conciliación financiera')
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
    cost_breakdown = fields.Text(string='Detalle de costos oficiales', readonly=True)
    state = fields.Selection([
        ('ok', 'Actualizado'), ('partial', 'Solo consumo local'), ('error', 'Error'),
    ], string='Estado', default='ok', required=True)
    source = fields.Selection([
        ('openai', 'OpenAI Platform'),
        ('local', 'Registro local de Odoo'),
        ('unavailable', 'No disponible'),
    ], string='Fuente del resumen', default='local', required=True, readonly=True)
    official_sync_at = fields.Datetime(
        string='Última consulta oficial', readonly=True,
        help='Momento en que Odoo consultó los endpoints oficiales de uso y costos.',
    )
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
    def _financial_values(self, cost, period_end):
        """Calcula un control interno, no el saldo oficial de OpenAI."""
        end_date = fields.Datetime.to_datetime(period_end).date()
        movements = self.env['chatroom.ai.funding'].sudo().search([
            ('company_id', '=', self.env.company.id),
            ('movement_date', '<=', end_date),
        ])
        credits = sum(m.amount for m in movements if m.movement_type == 'credit')
        debits = sum(m.amount for m in movements if m.movement_type == 'debit')
        currencies = set((m.currency or 'usd').lower() for m in movements)
        currency = next(iter(currencies), 'usd')
        net = credits - debits
        if currencies and len(currencies) > 1:
            return {
                'funding_total': credits, 'funding_debits': debits, 'funding_net': net,
                'estimated_balance': 0.0, 'funding_currency': currency,
                'funding_entry_count': len(movements), 'financial_state': 'mismatch',
                'billing_reconciliation_note': _('Hay movimientos en más de una moneda. Registra los fondos en USD para compararlos con el costo oficial de OpenAI.'),
            }
        estimated = net - max(float(cost or 0.0), 0.0)
        state = 'unconfigured' if not movements else 'available' if estimated >= 0 else 'exhausted'
        if not movements:
            note = _('No hay fondos registrados. Agrega cada recarga o ajuste en “Fondos y conciliación”.')
        elif not cost:
            note = _('El saldo de control usa los fondos registrados. Actualiza el costo oficial para obtener una comparación real del periodo consultado.')
        else:
            note = _('Control interno: fondos netos menos costo oficial del periodo. El saldo prepago real se confirma en la facturación de OpenAI.')
        return {
            'funding_total': credits, 'funding_debits': debits, 'funding_net': net,
            'estimated_balance': estimated, 'funding_currency': currency,
            'funding_entry_count': len(movements), 'financial_state': state,
            'billing_reconciliation_note': note,
        }

    @api.model
    def _fetch(self, path, key, start_ts, end_ts, group_by=None):
        params = {
            'start_time': start_ts,
            'end_time': end_ts,
            'bucket_width': '1d',
            'limit': 31,
        }
        if group_by:
            # OpenAI defines group_by as an array; requests serializes this
            # one-item list as the query parameter accepted by the API.
            params['group_by'] = [group_by] if isinstance(group_by, str) else group_by
        response = requests.get(
            '%s/%s' % (self._api_base(), path),
            headers={'Authorization': 'Bearer %s' % key},
            params=params,
            timeout=30,
        )
        if response.status_code >= 400:
            detail = ''
            try:
                payload = response.json()
                error_data = payload.get('error') if isinstance(payload, dict) else None
                if isinstance(error_data, dict):
                    detail = error_data.get('message') or ''
                elif error_data:
                    detail = str(error_data)
            except (ValueError, TypeError):
                detail = ''
            detail = detail or response.text[:300] or response.reason
            raise requests.HTTPError(
                'HTTP %s en %s: %s' % (response.status_code, path, detail),
                response=response,
            )
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    @api.model
    def _admin_api_key(self):
        return (self.env['ir.config_parameter'].sudo().get_param(
            'chatroom_whatsapp.ai_admin_api_key') or '').strip()

    @api.model
    def _set_sync_status(self, status, error=False):
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('chatroom_whatsapp.ai_usage_last_status', status)
        icp.set_param('chatroom_whatsapp.ai_usage_last_sync', fields.Datetime.now())
        icp.set_param('chatroom_whatsapp.ai_usage_last_error', error or '')

    @api.model
    def action_test_platform_connection(self):
        """Comprueba uso y costos oficiales sin generar una solicitud de IA."""
        admin_key = self._admin_api_key()
        if not admin_key:
            self._set_sync_status('missing_admin_key', _(
                'No se ha configurado la Admin API Key de OpenAI.'
            ))
            raise UserError(_(
                'Falta la Admin API Key de OpenAI. La API Key normal de Chatroom sirve '
                'para responder mensajes, pero no tiene el permiso api.usage.read para '
                'consultar uso y costos de la organización.'
            ))
        end_ts = int(datetime.utcnow().timestamp()) + 1
        start_ts = end_ts - 86400
        try:
            usage = self._fetch(
                'organization/usage/completions', admin_key, start_ts, end_ts,
                group_by='model',
            )
            costs = self._fetch(
                'organization/costs', admin_key, start_ts, end_ts,
                group_by='line_item',
            )
            requests_count = sum(
                int(result.get('num_model_requests') or 0)
                for bucket in usage.get('data', [])
                for result in bucket.get('results', [])
            )
            cost = sum(
                float((result.get('amount') or {}).get('value') or 0.0)
                for bucket in costs.get('data', [])
                for result in bucket.get('results', [])
            )
        except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
            self._set_sync_status('error', str(exc))
            raise UserError(_(
                'La Admin API Key no pudo consultar OpenAI Platform: %s. '
                'Verifica que sea una clave administrativa de la organización y que '
                'tenga acceso al proyecto.'
            ) % exc) from exc
        self._set_sync_status('ok')
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Conexión oficial correcta'),
                'message': _('OpenAI respondió. Últimas 24 h: %s solicitudes | costo %.6f USD.') % (
                    requests_count, cost),
                'type': 'success',
                'sticky': False,
            },
        }

    @api.model
    def action_refresh_local(self):
        """Genera un resumen inmediato desde las solicitudes registradas en Odoo."""
        now = fields.Datetime.now()
        start = now - timedelta(days=self._days())
        local_count, local_tokens = self._local_totals(start, now)
        values = {
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
            'cost_breakdown': '{}',
            'state': 'partial',
            'source': 'local',
            'error_message': _('Resumen local basado en las solicitudes registradas. Para costos oficiales configura la Admin API Key.'),
        }
        values.update(self._budget_values(0.0))
        values.update(self._financial_values(0.0, now))
        snapshot = self.sudo().create(values)
        snapshot._notify_budget_alert()
        return snapshot

    def action_refresh_local_ui(self):
        """Refresh local usage from a form/list button and open the result."""
        snapshot = self.env['chatroom.ai.usage.snapshot'].action_refresh_local()
        return snapshot._open_form_action()

    def _open_form_action(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Resumen de consumo de IA'),
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
        }

    @api.model
    def action_refresh(self):
        icp = self.env['ir.config_parameter'].sudo()
        admin_key = self._admin_api_key()
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
            'cost_breakdown': '{}',
        }
        values.update(self._budget_values(0.0))
        values.update(self._financial_values(0.0, now))
        if not admin_key:
            self._set_sync_status('missing_admin_key', _(
                'No se ha configurado la Admin API Key de OpenAI.'
            ))
            values.update({
                'state': 'partial',
                'source': 'local',
                'request_count': local_count,
                'total_tokens': local_tokens,
                'error_message': _('Configura una Admin API Key para consultar costos oficiales de la organización.'),
            })
            snapshot = self.sudo().create(values)
            snapshot._notify_budget_alert()
            return snapshot._open_form_action()

        start_ts = int(datetime.utcnow().timestamp()) - (self._days() * 86400)
        end_ts = int(datetime.utcnow().timestamp()) + 1
        try:
            usage = self._fetch('organization/usage/completions', admin_key, start_ts, end_ts, group_by='model')
            costs = self._fetch('organization/costs', admin_key, start_ts, end_ts, group_by='line_item')
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
            by_cost_line = {}
            for bucket in costs.get('data', []):
                for result in bucket.get('results', []):
                    amount = result.get('amount') or {}
                    line_cost = float(amount.get('value') or 0.0)
                    cost += line_cost
                    currency = amount.get('currency') or currency
                    line = result.get('line_item') or result.get('project_id') or _('Sin detalle')
                    by_cost_line[line] = by_cost_line.get(line, 0.0) + line_cost
            values.update({
                'request_count': request_count,
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'total_tokens': total_tokens,
                'cost': cost,
                'currency': currency,
                'model_breakdown': json.dumps(by_model, ensure_ascii=False, indent=2),
                'cost_breakdown': json.dumps(by_cost_line, ensure_ascii=False, indent=2),
                'state': 'ok',
                'source': 'openai',
                'official_sync_at': now,
                'error_message': False,
            })
            self._set_sync_status('ok')
            values.update(self._budget_values(cost))
            values.update(self._financial_values(cost, now))
            snapshot = self.sudo().create(values)
            snapshot._notify_budget_alert()
            return snapshot._open_form_action()
        except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
            self._set_sync_status('error', str(exc))
            values.update({'state': 'error', 'source': 'unavailable', 'error_message': str(exc)})
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

    def action_open_platform_billing(self):
        return {
            'type': 'ir.actions.act_url',
            'url': 'https://platform.openai.com/settings/organization/billing/overview',
            'target': 'new',
        }

# -*- coding: utf-8 -*-
import base64
import csv
import io
from collections import defaultdict
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

RFM_CATEGORIES = [
    ('a', "A - Alto valor"),
    ('b', "B - Valor medio"),
    ('c', "C - Bajo valor"),
    ('none', "Sin historial"),
]


class ResPartner(models.Model):
    _inherit = 'res.partner'

    commercial_invoice_count = fields.Integer(
        string="Cantidad de facturas", compute='_compute_commercial_metrics')
    commercial_total_sales = fields.Monetary(
        string="Total facturado (pagado)", compute='_compute_commercial_metrics',
        currency_field='currency_id',
        help="Suma de facturas de venta en estado 'Publicada' (out_invoice "
             "menos out_refund). A diferencia de 'Facturado' (total_invoiced, "
             "que excluye solo borrador/cancelada), este campo se calcula "
             "expresamente sobre estado 'posted' para reflejar ventas "
             "confirmadas, tal como lo pidió el equipo comercial.")
    commercial_last_sale_date = fields.Date(
        string="Última venta", compute='_compute_commercial_metrics')
    commercial_avg_ticket = fields.Monetary(
        string="Ticket promedio", compute='_compute_commercial_metrics',
        currency_field='currency_id')
    commercial_top_product_summary = fields.Char(
        string="Producto más comprado", compute='_compute_commercial_metrics')

    rfm_score = fields.Integer(
        string="Score RFM", default=0, copy=False, index=True,
        help="1 a 100. Se recalcula todos los días con el resto de la "
             "cartera de clientes (cron), no es un valor absoluto: es un "
             "percentil relativo de Recencia + Frecuencia + Monto.")
    rfm_category = fields.Selection(
        selection='_selection_rfm_category',
        string="Categoría RFM", default='none', copy=False, index=True,
        help="Clasificación simplificada A/B/C de valor del cliente, "
             "calculada por el mismo cron que el score RFM.")
    rfm_recency_days = fields.Integer(
        string="Recencia (días)", default=0, copy=False, readonly=True,
        help="Días transcurridos desde la última compra usada para el cálculo RFM.")
    rfm_frequency = fields.Integer(
        string="Frecuencia RFM", default=0, copy=False, readonly=True,
        help="Cantidad de compras consideradas por el cálculo RFM.")
    rfm_monetary_value = fields.Monetary(
        string="Valor monetario RFM", currency_field='currency_id', default=0.0,
        copy=False, readonly=True,
        help="Monto acumulado considerado por el cálculo RFM.")
    rfm_last_purchase_date = fields.Date(
        string="Última compra RFM", copy=False, readonly=True)
    rfm_last_computed_at = fields.Datetime(
        string="RFM calculado el", copy=False, readonly=True)
    rfm_recency_score = fields.Integer(
        string="Score Recencia", default=0, copy=False, readonly=True,
        help="Percentil 1-100 de recencia (100 = compró más recientemente "
             "que el resto de la cartera). Componente sin ponderar del "
             "score RFM compuesto, se guarda aparte para poder segmentar "
             "por comportamiento (ej. \"Champions\": alto en las 3 "
             "dimensiones) y no solo por el score final.")
    rfm_frequency_score = fields.Integer(
        string="Score Frecuencia", default=0, copy=False, readonly=True)
    rfm_monetary_score = fields.Integer(
        string="Score Monetario", default=0, copy=False, readonly=True)
    rfm_explanation = fields.Text(
        string="Explicación RFM", compute='_compute_rfm_explanation')

    @api.model
    def _selection_rfm_category(self):
        """Categorías configurables, conservando A/B/C como respaldo."""
        options = list(RFM_CATEGORIES)
        try:
            configured = self.env['crm.rfm.segment'].search([
                ('definition_type', '=', 'category'), ('active', '=', True),
            ], order='sequence, id')
            configured_options = [(category.code, category.name) for category in configured]
            known_codes = {code for code, _label in configured_options}
            options = configured_options + [item for item in options if item[0] not in known_codes]
        except Exception:  # puede no existir durante la carga inicial del registro
            pass
        return options

    @api.depends(
        'rfm_category', 'rfm_score', 'rfm_recency_days', 'rfm_frequency',
        'rfm_monetary_value', 'rfm_last_purchase_date',
    )
    def _compute_rfm_explanation(self):
        configured = self.env['crm.rfm.segment'].search([
            ('definition_type', '=', 'category'),
            ('active', '=', True),
        ])
        category_labels = dict(RFM_CATEGORIES)
        category_labels.update({category.code: category.name for category in configured})
        for partner in self:
            if not partner.rfm_frequency:
                partner.rfm_explanation = _(
                    'Sin compras válidas: todavía no hay datos suficientes para clasificar.')
                continue
            category = category_labels.get(partner.rfm_category, partner.rfm_category or '')
            partner.rfm_explanation = _(
                'Categoría %(category)s con score %(score)s. '
                'Última compra: %(last)s (%(recency)s días), '
                '%(frequency)s compras y %(amount)s de valor acumulado.'
            ) % {
                'category': category,
                'score': partner.rfm_score,
                'last': partner.rfm_last_purchase_date or _('sin fecha'),
                'recency': partner.rfm_recency_days,
                'frequency': partner.rfm_frequency,
                'amount': partner.rfm_monetary_value,
            }

    def action_schedule_rfm_followup(self):
        """Acción masiva: crea una actividad nativa para los contactos seleccionados."""
        activity_type = self.env['mail.activity.type'].search(
            [('category', '=', 'default')], order='sequence, id', limit=1)
        if not activity_type:
            raise UserError(_('No hay tipos de actividad configurados en Odoo.'))
        model_id = self.env['ir.model']._get_id('res.partner')
        deadline = fields.Date.add(fields.Date.context_today(self), days=3)
        existing = self.env['mail.activity'].search([
            ('res_model_id', '=', model_id), ('res_id', 'in', self.ids),
            ('summary', '=', _('Seguimiento RFM')),
            ('user_id', '=', self.env.user.id),
            ('date_deadline', '>=', fields.Date.context_today(self)),
        ])
        existing_ids = set(existing.mapped('res_id'))
        partners = self.filtered(lambda partner: partner.id not in existing_ids)
        if not partners:
            return {
                'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'title': _('Seguimientos'),
                           'message': _('Los clientes seleccionados ya tienen un seguimiento RFM abierto.'),
                           'type': 'info'},
            }
        self.env['mail.activity'].create([{
            'activity_type_id': activity_type.id,
            'summary': _('Seguimiento RFM'),
            'note': _('Revisar el segmento comercial y contactar al cliente.'),
            'date_deadline': deadline,
            'user_id': self.env.user.id,
            'res_model_id': model_id,
            'res_id': partner.id,
        } for partner in partners])
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'title': _('Actividades creadas'),
                       'message': _('%s seguimientos fueron programados.') % len(partners),
                       'type': 'success'},
        }

    @api.model
    def action_schedule_rfm_dashboard_followups(self, period='90', category='all', source='all'):
        """Schedule idempotent follow-ups for customers shown by the dashboard."""
        data = self.get_rfm_dashboard_data(period, category, include_all=True, source=source)
        ids = [row.get('id') for row in data.get('export_customers', []) if row.get('id')]
        if not ids:
            raise UserError(_('No hay clientes con compras en el filtro seleccionado.'))
        return self.browse(ids).action_schedule_rfm_followup()

    def _compute_commercial_metrics(self):
        Move = self.env['account.move']
        domain = [
            ('partner_id', 'in', self.ids),
            ('move_type', 'in', ('out_invoice', 'out_refund')),
            ('state', '=', 'posted'),
        ]
        grouped = Move._read_group(
            domain, groupby=['partner_id'],
            aggregates=['amount_total_signed:sum', '__count', 'invoice_date:max'])
        by_partner = {
            partner.id: (total, count, last_date)
            for partner, total, count, last_date in grouped
        }
        top_product_summaries = self._get_top_product_summaries()
        for partner in self:
            total, count, last_date = by_partner.get(partner.id, (0.0, 0, False))
            partner.commercial_invoice_count = count
            partner.commercial_total_sales = total
            partner.commercial_last_sale_date = last_date
            partner.commercial_avg_ticket = (total / count) if count else 0.0
            partner.commercial_top_product_summary = top_product_summaries.get(partner.id, False)

    def _get_top_product_summaries(self):
        """Return the top-product label for every partner in one query.

        This field is used in contact lists and in the CRM form. Calling
        ``_get_top_product_summary`` inside the compute loop caused one
        ``account.move.line`` query per contact (N+1), which became very
        noticeable as soon as the contact list contained more than a few
        records.
        """
        if not self:
            return {}
        grouped = self.env['account.move.line'].sudo()._read_group(
            [
                ('partner_id', 'in', self.ids),
                ('move_id.move_type', '=', 'out_invoice'),
                ('move_id.state', '=', 'posted'),
                ('product_id', '!=', False),
                ('display_type', '=', 'product'),
            ],
            groupby=['partner_id', 'product_id'],
            aggregates=['price_subtotal:sum'],
        )
        totals = defaultdict(lambda: defaultdict(float))
        for partner, product, amount in grouped:
            if partner and product:
                totals[partner.id][product.id] += amount or 0.0

        top_rows = []
        for partner_id, product_totals in totals.items():
            ranked = sorted(product_totals.items(), key=lambda item: item[1], reverse=True)
            if not ranked:
                continue
            grand_total = sum(product_totals.values())
            percentage = (ranked[0][1] / grand_total) * 100 if grand_total else 0.0
            top_rows.append((partner_id, ranked[0][0], percentage))
        products = self.env['product.product'].browse([row[1] for row in top_rows])
        products_by_id = {product.id: product for product in products}
        return {
            partner_id: "Top: %s (%s%% de sus compras)" % (
                products_by_id[product_id].display_name, round(percentage, 1))
            for partner_id, product_id, percentage in top_rows
        }

    def _get_top_products(self, limit=5):
        """Devuelve hasta `limit` productos comprados por el contacto,
        ordenados de mayor a menor monto, junto con el % que representan
        sobre el total comprado (análisis Pareto 80/20)."""
        self.ensure_one()
        grouped = self.env['account.move.line'].sudo()._read_group([
            ('partner_id', '=', self.id),
            ('move_id.move_type', '=', 'out_invoice'),
            ('move_id.state', '=', 'posted'),
            ('product_id', '!=', False),
            ('display_type', '=', 'product'),
        ], groupby=['product_id'], aggregates=['price_subtotal:sum'])
        totals = {product.id: amount or 0.0 for product, amount in grouped if product}
        grand_total = sum(totals.values())
        ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)
        product_ids = [product_id for product_id, _amount in ranked[:limit]]
        products_by_id = {
            product.id: product
            for product in self.env['product.product'].browse(product_ids)
        }
        result = []
        for product_id, amount in ranked[:limit]:
            product = products_by_id[product_id]
            result.append({
                'product_id': product.id,
                'product_name': product.display_name,
                'amount': amount,
                'percentage': round((amount / grand_total) * 100, 1) if grand_total else 0.0,
            })
        return result

    def _get_top_product_summary(self):
        self.ensure_one()
        top = self._get_top_products(limit=1)
        if not top:
            return False
        return "Top: %s (%s%% de sus compras)" % (top[0]['product_name'], top[0]['percentage'])

    def action_view_top_products(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': "Top productos (Pareto)",
            'res_model': 'account.invoice.report',
            'view_mode': 'list,pivot',
            'domain': [
                ('partner_id', '=', self.id),
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
            ],
            'context': {
                'search_default_group_by_product': 1,
                'group_by': ['product_id'],
            },
        }

    def action_create_rfm_marketing_list(self):
        """Crea (o completa) una lista de Email Marketing con los
        contactos seleccionados que tengan email cargado — pensado para
        usarse desde Contactos filtrando por Categoría RFM y
        seleccionando todo el resultado. No depende de mass_mailing:
        si el módulo no está instalado, avisa en vez de romper."""
        if 'mailing.list' not in self.env:
            raise UserError(_(
                "Esta acción necesita el módulo Email Marketing instalado "
                "(Ajustes > Apps > 'Email Marketing')."))

        partners_with_email = self.filtered('email')
        if not partners_with_email:
            raise UserError(_(
                "Ninguno de los contactos seleccionados tiene un email "
                "cargado; no se puede armar una lista de envío."))

        categories = set(partners_with_email.mapped('rfm_category'))
        today = fields.Date.context_today(self)
        if len(categories) == 1:
            code = categories.pop()
            category = self.env['crm.rfm.segment'].search([
                ('definition_type', '=', 'category'), ('code', '=', code),
            ], limit=1)
            label = category.name if category else dict(RFM_CATEGORIES).get(code, code)
            list_name = _("RFM - Categoría %(label)s - %(date)s") % {'label': label, 'date': today}
        else:
            list_name = _("RFM - Selección de contactos - %s") % today

        MailingContact = self.env['mailing.contact']
        mailing_list = self.env['mailing.list'].create({'name': list_name})
        for partner in partners_with_email:
            contact = MailingContact.search([('email', '=', partner.email)], limit=1)
            if not contact:
                contact = MailingContact.create({
                    'name': partner.name,
                    'email': partner.email,
                })
            if mailing_list.id not in contact.list_ids.ids:
                contact.list_ids = [(4, mailing_list.id)]

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mailing.list',
            'res_id': mailing_list.id,
            'view_mode': 'form',
            'target': 'current',
        }

    @api.model
    def action_recompute_rfm_dashboard(self):
        """Recalculate the portfolio from the dashboard with a clear response."""
        if not (
            self.env.user.has_group('sales_team.group_sale_manager')
            or self.env.user.has_group('base.group_system')
        ):
            raise UserError(_('Solo un gerente puede recalcular toda la cartera RFM.'))
        self.sudo()._cron_compute_rfm_scores()
        return True

    @api.model
    def action_export_rfm_dashboard_csv(self, period='90', category='all', source='all'):
        """Export the visible commercial summary without creating sales data."""
        data = self.get_rfm_dashboard_data(period, category, include_all=True, source=source)
        output = io.StringIO(newline='')
        writer = csv.writer(output)
        writer.writerow([
            _('Cliente'), _('Categoría RFM'), _('Score'),
            _('Ventas del período'), _('Facturas del período'),
        ])
        for row in data.get('export_customers', data.get('top_customers', [])):
            writer.writerow([
                row.get('name', ''), row.get('category', ''), row.get('score', 0),
                row.get('total', 0.0), row.get('invoice_count', 0),
            ])
        attachment = self.env['ir.attachment'].sudo().create({
            'name': 'resumen_rfm_%s.csv' % fields.Date.context_today(self),
            'type': 'binary',
            'datas': base64.b64encode(output.getvalue().encode('utf-8-sig')),
            'mimetype': 'text/csv',
            'res_model': 'res.partner',
            'res_id': self.env.user.partner_id.id,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'self',
        }

    @api.model
    def get_rfm_dashboard_data(self, period='90', category='all', include_all=False, source='all'):
        """Return configurable RFM and commercial KPIs for the dashboard."""
        today = fields.Date.context_today(self)
        date_from = False
        if period in ('30', '90', '365'):
            date_from = today - timedelta(days=int(period))

        partner_domain = []
        if category and category != 'all':
            partner_domain.append(('rfm_category', '=', category))
        partners = self.search(partner_domain)
        partner_ids = partners.ids

        invoice_domain = [
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('partner_id', 'in', partner_ids or [0]),
        ]
        if date_from:
            invoice_domain.append(('invoice_date', '>=', date_from))
        grouped = [] if source == 'history' else self.env['account.move']._read_group(
            invoice_domain, groupby=['partner_id'],
            aggregates=['amount_total_signed:sum', '__count'])

        metrics_by_partner = {}
        for partner, total, count in grouped:
            if not partner:
                continue
            metrics_by_partner[partner.id] = {
                'partner': partner, 'total': total or 0.0, 'invoice_count': count or 0,
            }
        external_rows = [] if source == 'native' else self._get_rfm_dashboard_external_rows(partner_ids, date_from)
        native_rows = [] if source == 'history' else self._get_rfm_native_rows(partner_ids, date_from)
        for item in external_rows + [
            {'partner': row['partner'], 'total': row['total'], 'invoice_count': row['count']}
            for row in native_rows
        ]:
            partner = item.get('partner')
            if not partner:
                continue
            current = metrics_by_partner.setdefault(partner.id, {
                'partner': partner, 'total': 0.0, 'invoice_count': 0,
            })
            current['total'] += item.get('total', 0.0) or 0.0
            current['invoice_count'] += item.get('invoice_count', 0) or 0
        customer_rows = [{
            'id': item['partner'].id,
            'name': item['partner'].display_name,
            'total': round(item['total'], 2),
            'invoice_count': item['invoice_count'],
            'category': item['partner'].rfm_category or 'none',
            'score': item['partner'].rfm_score or 0,
        } for item in metrics_by_partner.values()]
        customer_rows.sort(key=lambda row: row['total'], reverse=True)

        computed_dates = [value for value in partners.mapped('rfm_last_computed_at') if value]
        last_computed = max(computed_dates) if computed_dates else False

        total_sales = round(sum(row['total'] for row in customer_rows), 2)
        invoice_count = sum(row['invoice_count'] for row in customer_rows)
        previous_total = 0.0
        previous_invoice_count = 0
        if date_from:
            previous_from = date_from - timedelta(days=int(period))
            previous_domain = [
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
                ('partner_id', 'in', partner_ids or [0]),
                ('invoice_date', '>=', previous_from),
                ('invoice_date', '<', date_from),
            ]
            previous_group = [] if source == 'history' else self.env['account.move']._read_group(
                previous_domain, groupby=[],
                aggregates=['amount_total_signed:sum', '__count'])
            if previous_group:
                previous_total = round(previous_group[0][0] or 0.0, 2)
                previous_invoice_count = previous_group[0][1] or 0
            previous_external_rows = [] if source == 'native' else self._get_rfm_dashboard_external_rows(
                partner_ids, previous_from, date_from)
            previous_total += sum(
                item.get('total', 0.0) or 0.0 for item in previous_external_rows)
            previous_invoice_count += sum(
                item.get('invoice_count', 0) or 0 for item in previous_external_rows)
            previous_native_rows = [] if source == 'history' else self._get_rfm_native_rows(
                partner_ids, previous_from, date_from)
            previous_total += sum(row['total'] for row in previous_native_rows)
            previous_invoice_count += sum(row['count'] for row in previous_native_rows)
        sales_variation = round(
            ((total_sales - previous_total) / previous_total) * 100, 1
        ) if previous_total else False
        scored_partners = [partner for partner in partners if partner.rfm_score]
        average_score = round(
            sum(partner.rfm_score for partner in scored_partners) / len(scored_partners), 1
        ) if scored_partners else 0.0

        category_counts = {}
        category_sales = {}
        for row in customer_rows:
            category_counts[row['category']] = category_counts.get(row['category'], 0) + 1
            category_sales[row['category']] = round(
                category_sales.get(row['category'], 0.0) + row['total'], 2)

        line_domain = [
            ('move_id.move_type', '=', 'out_invoice'),
            ('move_id.state', '=', 'posted'),
            ('move_id.partner_id', 'in', partner_ids or [0]),
            ('product_id', '!=', False),
            ('display_type', '=', 'product'),
        ]
        if date_from:
            line_domain.append(('move_id.invoice_date', '>=', date_from))
        product_grouped = self.env['account.move.line']._read_group(
            line_domain,
            groupby=['product_id'],
            aggregates=['price_subtotal:sum', '__count'],
        )
        top_products = sorted(
            [
                {
                    'id': product.id,
                    'name': product.display_name,
                    'total': round(total or 0.0, 2),
                    'line_count': count,
                }
                for product, total, count in product_grouped if product
            ],
            key=lambda row: row['total'], reverse=True,
        )[:8]

        configured_categories = self.env['crm.rfm.segment'].get_dashboard_options()
        all_categories = [item['code'] for item in configured_categories]
        if 'none' not in all_categories:
            all_categories.append('none')
        labels = {item['code']: item['label'] for item in configured_categories}
        labels.setdefault('none', 'Sin historial')
        distribution = [
            {
                'category': value,
                'label': labels.get(value, value),
                'count': category_counts.get(value, 0),
                'sales': category_sales.get(value, 0.0),
            }
            for value in all_categories
        ]
        evolution = self._get_rfm_dashboard_evolution(
            partner_ids, category, source, today)
        return {
            'period': period,
            'date_from': date_from.isoformat() if date_from else False,
            'date_to': today.isoformat(),
            'category': category or 'all',
            'source': source or 'all',
            'customer_count': len(partners),
            'active_customer_count': len(customer_rows),
            'total_sales': total_sales,
            'invoice_count': invoice_count,
            'average_ticket': round(total_sales / invoice_count, 2) if invoice_count else 0.0,
            'comparison': {
                'previous_sales': previous_total,
                'previous_invoice_count': previous_invoice_count,
                'sales_variation': sales_variation,
            },
            'average_score': average_score,
            'at_risk_count': sum(
                category_counts.get(item['code'], 0) for item in configured_categories
                if item['is_at_risk']),
            'category_options': configured_categories,
            'distribution': distribution,
            'top_customers': customer_rows[:10],
            'export_customers': customer_rows if include_all else False,
            'top_products': top_products,
            'evolution': evolution,
            'last_computed_at': fields.Datetime.to_string(last_computed) if last_computed else False,
            'can_recompute': (
                self.env.user.has_group('sales_team.group_sale_manager')
                or self.env.user.has_group('base.group_system')
            ),
            'custom_kpis': self.env['crm.kpi.definition'].get_dashboard_values(period, category),
        }

    @api.model
    def _get_rfm_dashboard_evolution(self, partner_ids, category='all', source='all', today=False):
        """Return a stable 12-month series for the dashboard chart."""
        today = today or fields.Date.context_today(self)
        first_month = today.replace(day=1) - relativedelta(months=11)
        months = []
        cursor = first_month.replace(day=1)
        for _index in range(12):
            months.append(cursor)
            next_month = cursor.replace(day=28) + timedelta(days=4)
            cursor = next_month.replace(day=1)
        totals = {month.isoformat(): 0.0 for month in months}
        counts = {month.isoformat(): 0 for month in months}
        if source != 'history':
            moves = self.env['account.move'].search([
                ('move_type', '=', 'out_invoice'), ('state', '=', 'posted'),
                ('partner_id', 'in', partner_ids or [0]),
                ('invoice_date', '>=', first_month),
            ])
            for move in moves:
                month = (move.invoice_date or today).replace(day=1).isoformat()
                if month in totals:
                    totals[month] += move.amount_total_signed or 0.0
                    counts[month] += 1
        if source != 'native':
            rows = self._get_rfm_dashboard_evolution_external_rows(
                partner_ids, first_month, today + timedelta(days=1))
            for row in rows:
                date_value = row.get('date')
                if not date_value:
                    continue
                month = date_value.replace(day=1).isoformat()
                if month in totals:
                    totals[month] += row.get('total', 0.0) or 0.0
                    counts[month] += row.get('invoice_count', 1) or 1
        return [{
            'month': month.strftime('%Y-%m'),
            'label': month.strftime('%b %Y'),
            'total': round(totals[month.isoformat()], 2),
            'invoice_count': counts[month.isoformat()],
        } for month in months]

    @api.model
    def _get_rfm_dashboard_evolution_external_rows(self, partner_ids, date_from, date_to=False):
        return []

    def _get_rfm_weights(self):
        """Pesos configurables (Ajustes > Inteligencia de Clientes) del
        score RFM compuesto. Se normalizan dividiendo cada uno por la
        suma de los tres, así que no hace falta que el usuario los
        cargue sumando exactamente 1 -y si los tres quedaran en 0 (caso
        límite, ej. instalación recién hecha con el parámetro borrado a
        mano), se cae a los pesos por defecto de siempre para no dividir
        por cero."""
        icp = self.env['ir.config_parameter'].sudo()
        monetary = float(icp.get_param('crm_customer_intelligence.rfm_weight_monetary', 0.5) or 0.0)
        frequency = float(icp.get_param('crm_customer_intelligence.rfm_weight_frequency', 0.3) or 0.0)
        recency = float(icp.get_param('crm_customer_intelligence.rfm_weight_recency', 0.2) or 0.0)
        total = monetary + frequency + recency
        if total <= 0:
            return 0.5, 0.3, 0.2
        return monetary / total, frequency / total, recency / total

    def _get_rfm_category_method(self):
        icp = self.env['ir.config_parameter'].sudo()
        return icp.get_param('crm_customer_intelligence.rfm_category_method', 'threshold')

    @api.model
    def _get_rfm_native_rows(self, partner_ids=None, date_from=False, date_to=False):
        """Ventas de POS y pedidos confirmados-pero-aún-no-facturados,
        como fuentes nativas adicionales de venta: un negocio con punto de
        venta (POS instalado) o que confirma pedidos antes de facturar
        (`sale`, siempre presente porque es dependencia dura del módulo)
        de otra forma deja clientes activos sin historial solo porque
        `account.move` todavía no refleja esa venta.

        A propósito se excluyen los pedidos POS ya facturados
        (`account_move` seteado) y las órdenes de venta con alguna
        factura generada (`invoice_ids`): esa venta ya la cuenta la
        agregación de facturas, así que incluirla aquí también la
        contaría dos veces."""
        partner_domain = [('partner_id', 'in', partner_ids or [0])] if partner_ids is not None \
            else [('partner_id', '!=', False)]
        rows = {}

        def _merge(grouped):
            for partner, total, count, last_date in grouped:
                if not partner:
                    continue
                entry = rows.setdefault(partner.id, {
                    'partner': partner, 'total': 0.0, 'count': 0, 'last_date': False,
                })
                entry['total'] += total or 0.0
                entry['count'] += count or 0
                date_value = fields.Date.to_date(last_date) if last_date else False
                if date_value and (not entry['last_date'] or date_value > entry['last_date']):
                    entry['last_date'] = date_value

        if 'pos.order' in self.env:
            pos_domain = [('state', 'in', ('paid', 'done')), ('account_move', '=', False)] + partner_domain
            if date_from:
                pos_domain.append(('date_order', '>=', date_from))
            if date_to:
                pos_domain.append(('date_order', '<', date_to))
            _merge(self.env['pos.order']._read_group(
                pos_domain, groupby=['partner_id'],
                aggregates=['amount_total:sum', '__count', 'date_order:max']))

        sale_domain = [
            ('state', '=', 'sale'),
            ('invoice_status', 'in', ('to invoice', 'no')),
            ('invoice_ids', '=', False),
        ] + partner_domain
        if date_from:
            sale_domain.append(('date_order', '>=', date_from))
        if date_to:
            sale_domain.append(('date_order', '<', date_to))
        _merge(self.env['sale.order']._read_group(
            sale_domain, groupby=['partner_id'],
            aggregates=['amount_total:sum', '__count', 'date_order:max']))

        return list(rows.values())

    @api.model
    def _get_rfm_native_extra_rows(self, date_from=None, date_to=None):
        """Versión en diccionario de `_get_rfm_native_rows()`, con la misma
        forma que `_get_rfm_external_rows()`, para que el cron de scoring
        pueda fusionar ambas fuentes con el mismo helper."""
        return {
            row['partner'].id: row
            for row in self._get_rfm_native_rows(date_from=date_from, date_to=date_to)
        }

    @api.model
    def _get_rfm_external_rows(self):
        """Extension hook for optional historical data providers.

        Providers return ``{partner_id: {partner, total, count, last_date}}``.
        The core RFM module remains independent from imports, legacy systems,
        or any other source of commercial history.
        """
        return {}

    @api.model
    def _get_rfm_dashboard_external_rows(self, partner_ids, date_from=False, date_to=False):
        """Extension hook for optional historical dashboard sources."""
        return []

    def _assign_percentile_categories(self, rows):
        """Corta la cartera ya puntuada en A (20% superior), B (30%
        siguiente) y C (50% restante) -las proporciones de Pareto de la
        metodología RFM clásica, en vez de comparar cada score contra
        un umbral fijo. Con carteras muy chicas el 20%/30% exacto no
        siempre da un número entero de clientes; se redondea
        garantizando al menos 1 en A y 1 en B si hay margen, para no
        dejar esas categorías vacías por puro redondeo.

        Los códigos A/B/C usados como corte no están hardcodeados: se
        toman los 3 primeros códigos activos del catálogo (por
        `sequence`), así que si el usuario renombra/recodifica sus
        categorías (o instala un catálogo distinto) el método percentil
        sigue asignando categorías que existen de verdad en
        Configuración > Categorías RFM, en vez de escribir literales
        'a'/'b'/'c' que podrían no corresponder a ningún registro."""
        codes = self.env['crm.rfm.segment'].search(
            [('definition_type', '=', 'category'), ('active', '=', True)],
            order='sequence, id', limit=3).mapped('code')
        codes += [code for code in ('a', 'b', 'c') if code not in codes]
        code_a, code_b, code_c = codes[0], codes[1], codes[2]
        ordered = sorted(rows, key=lambda r: r['score'], reverse=True)
        total = len(ordered)
        a_cutoff = max(1, round(total * 0.2))
        b_cutoff = min(total, a_cutoff + max(1, round(total * 0.3)))
        for index, row in enumerate(ordered):
            if index < a_cutoff:
                row['category'] = code_a
            elif index < b_cutoff:
                row['category'] = code_b
            else:
                row['category'] = code_c

    def _assign_threshold_categories(self, rows):
        """Compara cada score contra los umbrales configurados en
        Categorías RFM (score_min/score_max, editables a mano); si
        ninguno coincide, cae a los umbrales de siempre (70/40/0)."""
        for row in rows:
            category_record = self.env['crm.rfm.segment'].category_for_score(row['score'])
            if category_record:
                row['category'] = category_record.code
            elif row['score'] >= 70:
                row['category'] = 'a'
            elif row['score'] >= 40:
                row['category'] = 'b'
            else:
                row['category'] = 'c'

    @api.model
    def _merge_rfm_rows(self, rows, rows_by_partner, extra_rows, today):
        """Fusiona un mapa {partner_id: {partner, total, count, last_date}}
        (fuente nativa adicional o proveedor externo vía hook) dentro de
        las listas `rows`/`rows_by_partner` que arma
        `_cron_compute_rfm_scores`, sumando totales/cantidades y
        quedándose con la fecha más reciente."""
        for partner_id, extra in extra_rows.items():
            if not extra.get('partner') or extra.get('total', 0.0) <= 0:
                continue
            row = rows_by_partner.get(partner_id)
            if not row:
                row = {
                    'partner': extra['partner'], 'total': 0.0,
                    'count': 0, 'recency_days': 9999, 'last_date': False,
                }
                rows.append(row)
                rows_by_partner[partner_id] = row
            row['total'] += extra.get('total', 0.0)
            row['count'] += extra.get('count', 0)
            last_date = extra.get('last_date')
            if last_date:
                extra_recency = (today - last_date).days
                row['recency_days'] = min(row['recency_days'], extra_recency)
                if not row.get('last_date') or last_date > row['last_date']:
                    row['last_date'] = last_date

    @api.model
    def _cron_compute_rfm_scores(self, date_from=None, date_to=None):
        """Clasificación RFM (Recencia / Frecuencia / Monto): se calcula en
        lote sobre toda la cartera porque el score es un percentil relativo
        entre clientes, no un umbral absoluto por contacto. Se clasifican
        contactos con al menos una factura publicada, una venta de POS o
        un pedido confirmado (`_get_rfm_native_rows`), más lo que aporten
        proveedores externos vía `_get_rfm_external_rows`.

        `date_from`/`date_to`, cuando se pasan (recálculo puntual desde
        `crm.rfm.recompute.wizard`), acotan las facturas y las fuentes
        nativas (POS/pedidos) a ese rango -para revisar cómo se veía la
        cartera en un período pasado. El cron diario normal no los usa
        (quedan en None), así que el comportamiento por defecto no
        cambia. Los proveedores externos (`_get_rfm_external_rows`, ej.
        históricos importados) no tienen filtro de fecha propio todavía
        y siempre se incluyen completos."""
        today = fields.Date.context_today(self)
        weight_monetary, weight_frequency, weight_recency = self._get_rfm_weights()
        invoice_domain = [
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('partner_id', '!=', False),
        ]
        if date_from:
            invoice_domain.append(('invoice_date', '>=', date_from))
        if date_to:
            invoice_domain.append(('invoice_date', '<', date_to))
        grouped = self.env['account.move']._read_group(
            invoice_domain,
            groupby=['partner_id'],
            aggregates=['amount_total_signed:sum', '__count', 'invoice_date:max'],
        )
        rows = []
        for partner, total, count, last_date in grouped:
            if not partner or total <= 0:
                continue
            recency_days = (today - last_date).days if last_date else 9999
            rows.append({
                'partner': partner, 'total': total, 'count': count,
                'recency_days': recency_days, 'last_date': last_date,
            })

        rows_by_partner = {row['partner'].id: row for row in rows}
        self._merge_rfm_rows(
            rows, rows_by_partner,
            self._get_rfm_native_extra_rows(date_from, date_to), today)
        self._merge_rfm_rows(rows, rows_by_partner, self._get_rfm_external_rows(), today)
        if not rows:
            self._reset_stale_rfm_values()
            return

        def _percentile_rank(values, value, higher_is_better=True):
            if len(values) <= 1:
                return 100
            sorted_values = sorted(values, reverse=higher_is_better)
            rank = sorted_values.index(value)
            return round((1 - rank / (len(sorted_values) - 1)) * 100)

        totals = [r['total'] for r in rows]
        counts = [r['count'] for r in rows]
        recencies = [r['recency_days'] for r in rows]

        for row in rows:
            monetary_score = _percentile_rank(totals, row['total'], higher_is_better=True)
            frequency_score = _percentile_rank(counts, row['count'], higher_is_better=True)
            recency_score = _percentile_rank(recencies, row['recency_days'], higher_is_better=False)
            row['monetary_score'] = monetary_score
            row['frequency_score'] = frequency_score
            row['recency_score'] = recency_score
            row['score'] = round(
                (monetary_score * weight_monetary)
                + (frequency_score * weight_frequency)
                + (recency_score * weight_recency)
            )

        if self._get_rfm_category_method() == 'percentile':
            self._assign_percentile_categories(rows)
        else:
            self._assign_threshold_categories(rows)

        processed_partner_ids = set()
        for row in rows:
            processed_partner_ids.add(row['partner'].id)
            row['partner'].write({
                'rfm_score': row['score'],
                'rfm_category': row['category'],
                'rfm_recency_days': row['recency_days'],
                'rfm_frequency': row['count'],
                'rfm_monetary_value': row['total'],
                'rfm_recency_score': row['recency_score'],
                'rfm_frequency_score': row['frequency_score'],
                'rfm_monetary_score': row['monetary_score'],
                'rfm_last_purchase_date': row.get('last_date') or (
                    today - timedelta(days=row['recency_days'])),
                'rfm_last_computed_at': fields.Datetime.now(),
            })
        self._reset_stale_rfm_values(processed_partner_ids)

    def _reset_stale_rfm_values(self, processed_partner_ids=None):
        """Remove scores left behind when a customer's last purchase is removed.

        This keeps the dashboard honest after cancelling an invoice or
        reverting an approved historical batch. Without this cleanup, a
        customer could retain an old A/B/C classification forever.
        """
        domain = [
            '|', '|', '|',
            ('rfm_score', '!=', 0),
            ('rfm_category', '!=', 'none'),
            ('rfm_frequency', '!=', 0),
            ('rfm_monetary_value', '!=', 0),
        ]
        if processed_partner_ids:
            domain.append(('id', 'not in', list(processed_partner_ids)))
        stale = self.search(domain)
        if stale:
            stale.write({
                'rfm_score': 0,
                'rfm_category': 'none',
                'rfm_recency_days': 0,
                'rfm_frequency': 0,
                'rfm_monetary_value': 0.0,
                'rfm_recency_score': 0,
                'rfm_frequency_score': 0,
                'rfm_monetary_score': 0,
                'rfm_last_purchase_date': False,
                'rfm_last_computed_at': fields.Datetime.now(),
            })

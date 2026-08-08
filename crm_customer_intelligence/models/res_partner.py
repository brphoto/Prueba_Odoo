# -*- coding: utf-8 -*-
from datetime import timedelta

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

    @api.model
    def _selection_rfm_category(self):
        """CategorÃ­as configurables, conservando A/B/C como respaldo."""
        options = list(RFM_CATEGORIES)
        try:
            configured = self.env['crm.rfm.category'].search([], order='sequence, id')
            configured_options = [(category.code, category.name) for category in configured]
            known_codes = {code for code, _label in configured_options}
            options = configured_options + [item for item in options if item[0] not in known_codes]
        except Exception:  # puede no existir durante la carga inicial del registro
            pass
        return options

    def action_schedule_rfm_followup(self):
        """Acción masiva: crea una actividad nativa para los contactos seleccionados."""
        activity_type = self.env['mail.activity.type'].search(
            [('category', '=', 'default')], order='sequence, id', limit=1)
        if not activity_type:
            raise UserError(_('No hay tipos de actividad configurados en Odoo.'))
        model_id = self.env['ir.model']._get_id('res.partner')
        deadline = fields.Date.add(fields.Date.context_today(self), days=3)
        self.env['mail.activity'].create([{
            'activity_type_id': activity_type.id,
            'summary': _('Seguimiento RFM'),
            'note': _('Revisar el segmento comercial y contactar al cliente.'),
            'date_deadline': deadline,
            'user_id': self.env.user.id,
            'res_model_id': model_id,
            'res_id': partner.id,
        } for partner in self])
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'title': _('Actividades creadas'),
                       'message': _('%s seguimientos fueron programados.') % len(self),
                       'type': 'success'},
        }

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
        for partner in self:
            total, count, last_date = by_partner.get(partner.id, (0.0, 0, False))
            partner.commercial_invoice_count = count
            partner.commercial_total_sales = total
            partner.commercial_last_sale_date = last_date
            partner.commercial_avg_ticket = (total / count) if count else 0.0
            partner.commercial_top_product_summary = partner._get_top_product_summary()

    def _get_top_products(self, limit=5):
        """Devuelve hasta `limit` productos comprados por el contacto,
        ordenados de mayor a menor monto, junto con el % que representan
        sobre el total comprado (análisis Pareto 80/20)."""
        self.ensure_one()
        lines = self.env['account.move.line'].sudo().search([
            ('move_id.partner_id', '=', self.id),
            ('move_id.move_type', '=', 'out_invoice'),
            ('move_id.state', '=', 'posted'),
            ('product_id', '!=', False),
            ('display_type', '=', 'product'),
        ])
        totals = {}
        for line in lines:
            totals.setdefault(line.product_id, 0.0)
            totals[line.product_id] += line.price_subtotal
        grand_total = sum(totals.values())
        ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)
        result = []
        for product, amount in ranked[:limit]:
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
            category = self.env['crm.rfm.category'].search([('code', '=', code)], limit=1)
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
    def get_rfm_dashboard_data(self, period='90', category='all'):
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
        grouped = self.env['account.move']._read_group(
            invoice_domain,
            groupby=['partner_id'],
            aggregates=['amount_total_signed:sum', '__count'],
        )

        customer_rows = []
        for partner, total, count in grouped:
            if not partner:
                continue
            customer_rows.append({
                'id': partner.id,
                'name': partner.display_name,
                'total': round(total or 0.0, 2),
                'invoice_count': count,
                'category': partner.rfm_category or 'none',
                'score': partner.rfm_score or 0,
            })
        customer_rows.sort(key=lambda row: row['total'], reverse=True)

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
            previous_group = self.env['account.move']._read_group(
                previous_domain, groupby=[],
                aggregates=['amount_total_signed:sum', '__count'])
            if previous_group:
                previous_total = round(previous_group[0][0] or 0.0, 2)
                previous_invoice_count = previous_group[0][1] or 0
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

        configured_categories = self.env['crm.rfm.category'].get_dashboard_options()
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
        return {
            'period': period,
            'date_from': date_from.isoformat() if date_from else False,
            'date_to': today.isoformat(),
            'category': category or 'all',
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
            'top_products': top_products,
            'custom_kpis': self.env['crm.kpi.definition'].get_dashboard_values(period, category),
        }

    @api.model
    def _cron_compute_rfm_scores(self):
        """Clasificación RFM (Recencia / Frecuencia / Monto): se calcula en
        lote sobre toda la cartera porque el score es un percentil relativo
        entre clientes, no un umbral absoluto por contacto. Solo se
        clasifican contactos con al menos una factura publicada."""
        today = fields.Date.context_today(self)
        grouped = self.env['account.move']._read_group(
            [
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
                ('partner_id', '!=', False),
            ],
            groupby=['partner_id'],
            aggregates=['amount_total_signed:sum', '__count', 'invoice_date:max'],
        )
        rows = []
        for partner, total, count, last_date in grouped:
            if not partner or total <= 0:
                continue
            recency_days = (today - last_date).days if last_date else 9999
            rows.append({'partner': partner, 'total': total, 'count': count, 'recency_days': recency_days})
        if not rows:
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
            score = round((monetary_score * 0.5) + (frequency_score * 0.3) + (recency_score * 0.2))
            category_record = self.env['crm.rfm.category'].category_for_score(score)
            if category_record:
                category = category_record.code
            elif score >= 70:
                category = 'a'
            elif score >= 40:
                category = 'b'
            else:
                category = 'c'
            row['partner'].write({'rfm_score': score, 'rfm_category': category})

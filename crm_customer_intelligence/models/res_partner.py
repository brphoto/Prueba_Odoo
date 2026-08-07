# -*- coding: utf-8 -*-
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
        string="Score RFM", default=0, copy=False,
        help="1 a 100. Se recalcula todos los días con el resto de la "
             "cartera de clientes (cron), no es un valor absoluto: es un "
             "percentil relativo de Recencia + Frecuencia + Monto.")
    rfm_category = fields.Selection(
        RFM_CATEGORIES, string="Categoría RFM (ABC)", default='none', copy=False,
        help="Clasificación simplificada A/B/C de valor del cliente, "
             "calculada por el mismo cron que el score RFM.")

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
            label = dict(self._fields['rfm_category'].selection).get(categories.pop())
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
            if score >= 70:
                category = 'a'
            elif score >= 40:
                category = 'b'
            else:
                category = 'c'
            row['partner'].write({'rfm_score': score, 'rfm_category': category})

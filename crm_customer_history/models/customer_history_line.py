import hashlib
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CrmCustomerHistoryLine(models.Model):
    _name = 'crm.customer.history.line'
    _description = 'Detalle de histórico comercial'
    _order = 'batch_id, row_number, id'

    batch_id = fields.Many2one(
        'crm.customer.history.batch', required=True, ondelete='cascade', index=True,
        string='Lote')
    company_id = fields.Many2one(
        related='batch_id.company_id', store=True, index=True, string='Empresa')
    row_number = fields.Integer(string='Fila', readonly=True, index=True)
    customer_name = fields.Char(string='Nombre del cliente', readonly=True)
    customer_external_ref = fields.Char(string='Código externo', readonly=True)
    customer_vat = fields.Char(string='RUC / Identificación', readonly=True)
    customer_email = fields.Char(string='Correo', readonly=True)
    customer_phone = fields.Char(string='Teléfono', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Cliente', index=True)
    suggested_partner_ids = fields.Many2many(
        'res.partner', compute='_compute_suggested_partners',
        string='Posibles coincidencias', help='Contactos que coinciden por RUC, correo o nombre.')
    partner_match_state = fields.Selection([
        ('matched', 'Encontrado'),
        ('created', 'Creado'),
        ('unmatched', 'Sin identificar'),
    ], string='Identificación', default='unmatched', readonly=True)
    invoice_number = fields.Char(string='Número de factura', readonly=True)
    invoice_date = fields.Date(string='Fecha de factura', readonly=True)
    move_type = fields.Selection([
        ('sale', 'Venta'),
        ('refund', 'Devolución'),
    ], string='Tipo', default='sale', readonly=True)
    amount_total = fields.Float(string='Monto', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Moneda', readonly=True)
    company_amount_total = fields.Monetary(
        string='Monto en moneda de la empresa', currency_field='company_currency_id',
        compute='_compute_company_amount_total', store=True, readonly=True)
    company_currency_id = fields.Many2one(
        related='company_id.currency_id', string='Moneda de la empresa', readonly=True)
    fingerprint = fields.Char(string='Huella', index=True, readonly=True)
    state = fields.Selection([
        ('valid', 'Válido'),
        ('error', 'Error'),
        ('duplicate', 'Duplicado'),
    ], string='Estado', default='error', index=True, readonly=True)
    error_message = fields.Text(string='Detalle del error', readonly=True)

    @api.depends('customer_name', 'customer_vat', 'customer_email', 'customer_phone', 'partner_id')
    @staticmethod
    def _match_keys(line):
        """Claves normalizadas por las que se busca un contacto."""
        keys = []
        if line.customer_vat:
            keys.append(('vat', line.customer_vat.strip().lower()))
        if line.customer_email:
            keys.append(('email', line.customer_email.strip().lower()))
        if line.customer_name:
            keys.append(('name', line.customer_name.strip().lower()))
        return keys

    def _candidate_partners(self):
        """{(campo, valor en minusculas): ids de contacto} para todo el lote.

        Antes se hacia una busqueda por linea. Una importacion de historico
        trae miles de lineas, asi que eran miles de consultas solo para
        pintar la columna de sugerencias. Ahora es una por campo.

        Se usa SQL directo porque el original comparaba con `=ilike`, que
        sin comodines es una igualdad sin distinguir mayusculas: `lower()`
        en ambos lados da exactamente el mismo resultado, cosa que un
        dominio `in` del ORM no haria.
        """
        wanted = {}
        for line in self:
            for field, value in self._match_keys(line):
                wanted.setdefault(field, set()).add(value)
        if not wanted:
            return {}
        self.env['res.partner'].flush_model(['vat', 'email', 'name', 'active'])
        candidates = {}
        for field, values in wanted.items():
            if not values:
                continue
            self.env.cr.execute(
                "SELECT lower(%s), id FROM res_partner "
                " WHERE active = true AND lower(%s) IN %%s" % (field, field),
                (tuple(values),))
            for value, partner_id in self.env.cr.fetchall():
                candidates.setdefault((field, value), []).append(partner_id)
        return candidates

    def _compute_suggested_partners(self):
        Partner = self.env['res.partner']
        candidates = self._candidate_partners()
        for line in self:
            if line.partner_id:
                line.suggested_partner_ids = Partner
                continue
            keys = self._match_keys(line)
            if not keys:
                line.suggested_partner_ids = Partner
                continue
            matches = Partner
            for key in keys:
                matches |= Partner.browse(candidates.get(key, ()))
            # Se conserva el limite de 5: la ficha muestra sugerencias,
            # no un listado completo.
            line.suggested_partner_ids = matches[:5]

    def action_use_suggested_partner(self):
        self.ensure_one()
        if len(self.suggested_partner_ids) != 1:
            raise UserError(_('Debe existir una sola coincidencia sugerida para aplicarla.'))
        self.write({
            'partner_id': self.suggested_partner_ids.id,
            'partner_match_state': 'matched',
            'state': 'valid',
            'error_message': False,
        })
        return True

    @api.depends('amount_total', 'currency_id', 'company_id', 'invoice_date', 'move_type')
    def _compute_company_amount_total(self):
        for line in self:
            amount = line.amount_total or 0.0
            if line.move_type == 'refund':
                amount *= -1
            if line.currency_id and line.company_id and line.currency_id != line.company_id.currency_id:
                amount = line.currency_id._convert(
                    amount, line.company_id.currency_id, line.company_id,
                    line.invoice_date or fields.Date.context_today(line))
            line.company_amount_total = amount

    @api.model
    def make_fingerprint(self, values):
        """Stable key for reloading the same source without duplication."""
        parts = [
            str(values.get('company_id') or ''),
            str(values.get('partner_id') or ''),
            str(values.get('customer_external_ref') or '').strip().lower(),
            str(values.get('customer_vat') or '').strip().lower(),
            str(values.get('invoice_number') or '').strip().lower(),
            str(values.get('invoice_date') or ''),
            str(values.get('amount_total') or 0),
            str(values.get('move_type') or 'sale'),
        ]
        return hashlib.sha1('|'.join(parts).encode('utf-8')).hexdigest()

    @staticmethod
    def normalize_phone(value):
        return re.sub(r'\D', '', str(value or ''))

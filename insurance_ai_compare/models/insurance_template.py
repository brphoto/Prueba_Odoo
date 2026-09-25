# -*- coding: utf-8 -*-
import re
import unicodedata

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


def normalize_text(value):
    """Minúsculas, sin tildes ni signos: para comparar nombres de coberturas."""
    value = unicodedata.normalize('NFKD', value or '')
    value = ''.join(char for char in value if not unicodedata.combining(char))
    return re.sub(r'[^a-z0-9]+', ' ', value.lower()).strip()


class InsuranceCompareTemplate(models.Model):
    """Cómo se compara un ramo: coberturas, pesos, reglas y datos del cliente."""
    _name = 'insurance.compare.template'
    _description = 'Plantilla de comparativo de seguros'
    _order = 'sequence, name'

    name = fields.Char(string='Nombre', required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', string='Empresa', default=lambda self: self.env.company,
        help='Vacío: disponible en todas las empresas.')
    ramo_id = fields.Many2one(
        'poliza.ramo', string='Ramo',
        help='Se propone automáticamente en los comparativos de este ramo.')
    coverage_ids = fields.One2many(
        'insurance.coverage', 'template_id', string='Coberturas a comparar', copy=True)

    weight_price = fields.Float(string='Peso del precio (%)', default=35.0)
    weight_deductible = fields.Float(string='Peso del deducible (%)', default=20.0)
    weight_coverage = fields.Float(string='Peso de las coberturas (%)', default=35.0)
    weight_service = fields.Float(
        string='Peso de asistencias y servicio (%)', default=10.0,
        help='Asistencias incluidas y la calificación de servicio de la aseguradora.')

    extraction_instructions = fields.Text(
        string='Instrucciones de extracción',
        help='Qué debe buscar la IA en las cotizaciones de este ramo, además de lo general.')
    profile_fields = fields.Text(
        string='Datos del cliente a recopilar',
        help='Uno por línea con el formato clave: descripción. La IA los busca en '
             'la conversación (/perfil) y pide los que falten (/faltantes).\n'
             'Ej.: marca: Marca del vehículo')
    legal_note = fields.Text(
        string='Nota legal del PDF',
        default=lambda self: _(
            'Este comparativo es una recomendación del asesor basada en las cotizaciones '
            'recibidas y los datos entregados por el cliente. Las condiciones definitivas '
            'son las de la póliza emitida por la aseguradora. Revise exclusiones, '
            'deducibles y condiciones particulares antes de contratar.'))
    weight_total = fields.Float(compute='_compute_weight_total', string='Suma de pesos')

    @api.depends('weight_price', 'weight_deductible', 'weight_coverage', 'weight_service')
    def _compute_weight_total(self):
        for template in self:
            template.weight_total = (template.weight_price + template.weight_deductible
                                     + template.weight_coverage + template.weight_service)

    @api.constrains('weight_price', 'weight_deductible', 'weight_coverage', 'weight_service')
    def _check_weights(self):
        for template in self:
            weights = (template.weight_price, template.weight_deductible,
                       template.weight_coverage, template.weight_service)
            if any(weight < 0 for weight in weights):
                raise ValidationError(_('Los pesos no pueden ser negativos.'))
            if not sum(weights):
                raise ValidationError(_('Al menos un peso debe ser mayor que cero.'))

    def _profile_field_list(self):
        """[(clave, descripción)] a partir del texto «clave: descripción»."""
        self.ensure_one()
        result = []
        for line in (self.profile_fields or '').splitlines():
            if not line.strip():
                continue
            key, _sep, label = line.partition(':')
            key = normalize_text(key).replace(' ', '_')
            if key:
                result.append((key, (label or key).strip()))
        return result

    def _match_coverage(self, *names):
        """Cobertura del catálogo que corresponde a alguno de los nombres dados."""
        self.ensure_one()
        wanted = {normalize_text(name) for name in names if name}
        wanted.discard('')
        if not wanted:
            return self.env['insurance.coverage']
        for coverage in self.coverage_ids:
            if wanted & coverage._all_names():
                return coverage
        # Coincidencia parcial: "responsabilidad civil extracontractual" ⊃ "responsabilidad civil".
        for coverage in self.coverage_ids:
            for name in coverage._all_names():
                if len(name) > 3 and any(name in value for value in wanted):
                    return coverage
        return self.env['insurance.coverage']


class InsuranceCoverage(models.Model):
    """Cobertura normalizada: cada aseguradora la llama distinto."""
    _name = 'insurance.coverage'
    _description = 'Cobertura normalizada'
    _order = 'sequence, id'

    template_id = fields.Many2one(
        'insurance.compare.template', string='Plantilla', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    name = fields.Char(string='Cobertura', required=True)
    synonyms = fields.Text(
        string='Sinónimos',
        help='Otros nombres con que aparece en las cotizaciones, uno por línea o '
             'separados por coma. Ej.: RC, daños a terceros.')
    weight = fields.Float(
        string='Importancia', default=1.0,
        help='Peso de esta cobertura dentro del puntaje de coberturas.')
    required = fields.Boolean(
        string='Obligatoria',
        help='Una oferta que no la incluya queda descartada del ranking.')
    description = fields.Char(string='Qué cubre')

    def _all_names(self):
        self.ensure_one()
        names = {normalize_text(self.name)}
        for synonym in re.split(r'[\n,;]+', self.synonyms or ''):
            if synonym.strip():
                names.add(normalize_text(synonym))
        names.discard('')
        return names

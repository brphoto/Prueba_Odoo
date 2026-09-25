# -*- coding: utf-8 -*-
import base64
import io
import json

from odoo.tests import TransactionCase


def make_pdf(lines):
    """PDF real de una página con las líneas dadas (reportlab viene con Odoo)."""
    from reportlab.pdfgen import canvas
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    y = 800
    for line in lines:
        pdf.drawString(40, y, line)
        y -= 18
    pdf.save()
    return base64.b64encode(buffer.getvalue())


# Lo que "devuelve la IA" por aseguradora. La C no incluye responsabilidad
# civil (obligatoria): debe quedar descartada aunque sea la más barata.
EXTRACTIONS = {
    'Aseguradora Norte QA': {
        'prima_neta': 800, 'prima_total': '$ 920,00', 'forma_pago': '10 cuotas', 'cuotas': 10,
        'suma_asegurada': '18.500', 'deducible': {'texto': '10% del siniestro, mínimo $250', 'monto': 250},
        'coberturas': [
            {'nombre': 'Pérdida total por choque', 'catalogo': 'Pérdida total por daño', 'incluida': 'si',
             'limite': '100% valor comercial', 'pagina': 1, 'cita': 'Pérdida total por choque', 'confianza': 0.95},
            {'nombre': 'Daños a terceros', 'catalogo': None, 'incluida': 'si', 'limite': '30.000',
             'pagina': 1, 'cita': 'Daños a terceros hasta 30.000', 'confianza': 0.9},
            {'nombre': 'Auto de reemplazo', 'catalogo': None, 'incluida': 'si', 'limite': '10 días',
             'pagina': 2, 'confianza': 0.6},
        ],
        'asistencias': ['Grúa 24/7', 'Cerrajería', 'Auxilio mecánico'],
        'exclusiones': ['Conductor sin licencia'], 'confianza': 0.9,
    },
    'Aseguradora Sur QA': {
        'prima_neta': 900, 'prima_total': 1050, 'forma_pago': 'Contado',
        'suma_asegurada': 18500, 'deducible': {'texto': '$ 150', 'monto': '150'},
        'coberturas': [
            {'nombre': 'Pérdida total por daño', 'catalogo': 'Pérdida total por daño', 'incluida': 'si',
             'pagina': 1, 'confianza': 0.95},
            {'nombre': 'Responsabilidad civil', 'catalogo': 'Responsabilidad civil', 'incluida': 'si',
             'limite': '50.000', 'pagina': 1, 'confianza': 0.95},
            {'nombre': 'Muerte accidental ocupantes', 'catalogo': 'Muerte accidental de ocupantes',
             'incluida': 'limitada', 'limite': '5.000 por ocupante', 'pagina': 1, 'confianza': 0.9},
        ],
        'asistencias': ['Grúa'], 'exclusiones': [], 'confianza': 0.85,
    },
    'Aseguradora Oeste QA': {
        'prima_neta': 600, 'prima_total': 690, 'forma_pago': 'Contado',
        'deducible': {'texto': '$ 500', 'monto': 500},
        'coberturas': [
            {'nombre': 'Pérdida total por daño', 'catalogo': 'Pérdida total por daño', 'incluida': 'si',
             'pagina': 1, 'confianza': 0.9},
            {'nombre': 'Responsabilidad civil', 'catalogo': 'Responsabilidad civil', 'incluida': 'no',
             'pagina': 1, 'confianza': 0.9},
        ],
        'asistencias': [], 'exclusiones': [], 'confianza': 0.8,
    },
}


def fake_complete_factory(extractions=None, analysis=None, calls=None):
    """Simula chatroom.ai.service.complete según el mensaje recibido."""
    extractions = extractions or EXTRACTIONS

    def fake_complete(service, messages, task_type='document', model_id=None, timeout=120):
        if calls is not None:
            calls.append(messages)
        user = messages[-1]['content']
        for insurer, data in extractions.items():
            if user.startswith('Cotización de %s' % insurer):
                if isinstance(data, Exception):
                    raise data
                return json.dumps(data)
        if 'Cotizaciones (datos revisados por el asesor)' in user:
            return json.dumps(analysis or {
                'recomendacion': {'aseguradora': 'Aseguradora Norte QA',
                                  'motivo': 'Mejor equilibrio entre precio y coberturas.'},
                'resumen': 'Norte ofrece auto de reemplazo y más asistencias.',
                'ofertas': [
                    {'aseguradora': 'Aseguradora Norte QA', 'ventajas': ['Auto de reemplazo'],
                     'desventajas': ['Deducible mayor que Sur'], 'mejorar': ['Bajar el deducible a $150']},
                    {'aseguradora': 'Aseguradora Sur QA', 'ventajas': ['RC de 50.000'],
                     'desventajas': ['Sin auto de reemplazo'], 'mejorar': ['Incluir auto sustituto']},
                ],
                'explicacion_cliente': 'Te recomiendo Norte por su auto de reemplazo.',
            })
        raise AssertionError('Consulta de IA inesperada: %s' % user[:80])
    return fake_complete


class InsuranceCompareCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['ir.config_parameter'].sudo().set_param('insurance_ai_compare.require_consent', 'True')
        cls.template = cls.env.ref('insurance_ai_compare.template_vehicles')
        cls.partner = cls.env['res.partner'].create({'name': 'Cliente Seguros QA', 'phone': '+593990007000'})
        cls.env['ec.data.consent'].create({
            'partner_id': cls.partner.id,
            'consent_type_id': cls.env.ref('insurance_ai_compare.consent_type_asesoria_ia').id,
            'signed_by': 'Cliente Seguros QA',
        })
        Insurer = cls.env['polizas.aseguradoras']
        cls.insurers = {name: Insurer.create({'name': name, 'service_score': score})
                        for name, score in (('Aseguradora Norte QA', 4.5), ('Aseguradora Sur QA', 3.0),
                                            ('Aseguradora Oeste QA', 2.0))}

    def _compare(self, insurers=None, partner=None):
        insurers = insurers or list(self.insurers)
        return self.env['insurance.compare'].create({
            'partner_id': (partner or self.partner).id,
            'template_id': self.template.id,
            'priorities': 'Auto de reemplazo',
            'offer_ids': [(0, 0, {
                'insurer_id': self.insurers[name].id,
                'document': make_pdf(['Cotización %s' % name, 'Prima total: 920,00']),
                'document_name': '%s.pdf' % name,
            }) for name in insurers],
        })

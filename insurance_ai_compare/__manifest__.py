# -*- coding: utf-8 -*-
{
    'name': 'Comparativo de seguros con IA',
    'summary': 'Sube cotizaciones de varias aseguradoras y obtén cuadro comparativo, recomendación y PDF',
    'description': '''
Comparativo de cotizaciones de seguros asistido por IA para brokers:

* Sube los PDF de cada aseguradora: la IA extrae primas, deducibles, coberturas,
  asistencias y exclusiones, cada dato con su página de origen.
* Catálogo de coberturas por ramo con sinónimos para comparar lo mismo con lo mismo.
* Revisión humana de lo dudoso antes de usarlo.
* Puntaje calculado por Odoo (no por la IA) con pesos por ramo y reglas mínimas.
* Análisis: ventajas, desventajas, recomendación y qué debería mejorar cada aseguradora.
* PDF para el cliente y PDF interno de negociación; envío por WhatsApp o email.
* Convierte la opción elegida en póliza.
* Asesoría desde el chat: /perfil, /faltantes, /asesorar, /explicar, /comparativo.
* Consentimiento LOPDP obligatorio antes de tratar datos del cliente con IA.
''',
    'version': '19.0.1.0.0',
    'category': 'Sales/CRM',
    'author': 'Bryan Cando',
    'license': 'LGPL-3',
    'icon': '/insurance_ai_compare/static/description/icon.svg',
    'depends': ['polizas_partner', 'chatroom_ai', 'ec_data_consent', 'mail'],
    'external_dependencies': {'python': ['pypdf']},
    'data': [
        'security/insurance_security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/ir_cron_data.xml',
        'data/consent_type_data.xml',
        'data/insurance_template_data.xml',
        'data/quick_action_data.xml',
        'report/insurance_compare_report.xml',
        'wizard/insurance_policy_wizard_views.xml',
        'views/insurance_template_views.xml',
        'views/insurance_insurer_views.xml',
        'views/insurance_profile_views.xml',
        'views/insurance_compare_views.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'insurance_ai_compare/static/src/insurance_compare.scss',
        ],
        'web.assets_tests': [
            'insurance_ai_compare/static/tests/tours/insurance_compare_tour.js',
        ],
    },
    'installable': True,
    'application': True,
}

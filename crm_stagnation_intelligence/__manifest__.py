# -*- coding: utf-8 -*-
{
    'name': 'Inteligencia Comercial - Salud del Pipeline',
    'summary': 'Une RFM, oportunidades estancadas y capital atrapado en una vista integral.',
    'description': """
Capa de integración para Inteligencia Comercial.

No duplica cálculos: utiliza el motor RFM de crm_customer_intelligence y
el motor de estancamiento de crm_stagnation_management. Agrega una vista
única para priorizar clientes y oportunidades, además de indicadores en
la ficha del contacto.
    """,
    'author': 'Bryan Cando',
    'license': 'LGPL-3',
    'category': 'Sales/CRM',
    'version': '19.0.1.0.0',
    'depends': ['crm_customer_intelligence', 'crm_stagnation_management'],
    'data': [
        'views/crm_integrated_intelligence_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}

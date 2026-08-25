# -*- coding: utf-8 -*-
{
    'name': 'Automatizaciones Comerciales',
    'summary': 'Cumpleaños, recordatorios y avisos personalizados por fecha o vencimiento.',
    'description': """
Automatizaciones Comerciales
============================

Permite crear recordatorios profesionales y parametrizables para clientes,
facturas, oportunidades y eventos personalizados. Cada automatización puede
tener varias etapas de aviso (por ejemplo 14, 7 y 1 días antes), filtros por
segmentación RFM y canales de actividad, notificación, correo o WhatsApp.

WhatsApp es una integración opcional: si Chatroom está instalado, se puede
usar una plantilla aprobada de Meta sin convertirla en una dependencia del
motor principal.
    """,
    'author': 'Bryan Cando',
    'license': 'LGPL-3',
    'category': 'Sales/CRM',
    'version': '19.0.1.0.2',
    'depends': ['crm_customer_intelligence', 'mail', 'account'],
    'data': [
        'security/crm_engagement_security.xml',
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'data/engagement_automation_data.xml',
        'views/crm_engagement_views.xml',
        'views/res_partner_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}

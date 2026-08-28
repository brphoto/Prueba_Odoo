# -*- coding: utf-8 -*-
{
    'name': 'Experiencia del cliente (NPS + LTV)',
    'summary': 'Satisfacción NPS, valor de vida del cliente y segmentos estratégicos.',
    'description': 'Amplía Inteligencia Comercial sin duplicar RFM: Encuesta NPS nativa, LTV desde facturas, invitaciones postventa y cruce NPS + RFM.',
    'author': 'Bryan Cando', 'license': 'LGPL-3', 'category': 'Sales/CRM', 'version': '19.0.1.0.0',
    'depends': ['crm_customer_intelligence', 'survey'],
    'data': [
        'security/ir.model.access.csv', 'data/survey_nps_data.xml', 'data/ir_cron_data.xml',
        'views/nps_response_views.xml', 'views/nps_invitation_views.xml',
        'views/nps_campaign_views.xml',
        'views/experience_snapshot_views.xml', 'views/res_partner_views.xml',
        'views/res_config_settings_views.xml', 'views/menus.xml',
    ],
    'demo': [], 'installable': True, 'application': False, 'auto_install': False,
}
